"""Pre-publish Oracle — analyze draft content against the existing ecosystem.

Checks for topic overlap, cluster saturation, and provides a publish/update/skip
verdict via Claude API before new content goes live.
"""

import logging
from uuid import UUID

import asyncpg
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.config import get_settings
from app.utils.llm_cost import log_llm_usage
from app.utils.rate_limiter import RateLimiter
from app.utils.token_guard import truncate_for_api

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-20250514"
EMBEDDING_MODEL = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.5  # Cosine distance — lower = more similar


class PrePublishOracle:
    """Analyze new content against the existing ecosystem before publishing."""

    def __init__(self) -> None:
        settings = get_settings()
        self.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=5)

    async def analyze(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        draft_text: str | None = None,
        target_keyword: str | None = None,
    ) -> dict:
        """Run pre-publish analysis against the existing content ecosystem.

        Args:
            db: Database connection.
            site_id: Site to analyze against.
            draft_text: Optional draft content text.
            target_keyword: Optional target keyword to check.

        Returns:
            OracleVerdict dict with confidence, verdict, reasoning, similar posts,
            cluster state, and recommendation.
        """
        if not draft_text and not target_keyword:
            raise ValueError("At least one of draft_text or target_keyword is required")

        logger.info(
            "Oracle analysis for site %s (draft=%s, keyword=%s)",
            site_id,
            "yes" if draft_text else "no",
            target_keyword or "none",
        )

        similar_posts: list[dict] = []
        keyword_posts: list[dict] = []

        # 1. Embedding similarity search
        if draft_text:
            similar_posts = await self._find_similar_by_embedding(
                db, site_id, draft_text,
            )

        # 2. GSC keyword check
        if target_keyword:
            keyword_posts = await self._find_by_keyword(
                db, site_id, target_keyword,
            )

        # Merge and deduplicate
        all_similar = self._merge_similar(similar_posts, keyword_posts)

        # 3. Determine cluster context
        cluster_state = await self._get_cluster_context(db, all_similar)

        # 4. Generate verdict via Claude
        verdict_data = await self._generate_verdict(
            db=db,
            site_id=site_id,
            draft_text=draft_text,
            target_keyword=target_keyword,
            similar_posts=all_similar,
            cluster_state=cluster_state,
        )

        return verdict_data

    async def _find_similar_by_embedding(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        draft_text: str,
    ) -> list[dict]:
        """Find similar existing posts via embedding cosine similarity."""
        # Generate embedding for draft
        truncated = truncate_for_api(draft_text, max_chars=20000, label="oracle_embedding")
        try:
            resp = await self.openai.embeddings.create(
                model=EMBEDDING_MODEL,
                input=truncated,
            )
            draft_embedding = resp.data[0].embedding
        except Exception as e:
            logger.error("Failed to generate draft embedding: %s", e)
            return []

        await log_llm_usage(
            db, site_id=site_id, service="oracle_embedding",
            model=EMBEDDING_MODEL, input_tokens=resp.usage.total_tokens,
        )

        # Format as pgvector
        vec_str = "[" + ",".join(str(v) for v in draft_embedding) + "]"

        # Query similar posts
        rows = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count, p.publish_date,
                   pe.embedding <=> $1::vector AS distance
            FROM post_embeddings pe
            JOIN posts p ON p.id = pe.post_id
            WHERE p.site_id = $2
            ORDER BY pe.embedding <=> $1::vector
            LIMIT 20
            """,
            vec_str, site_id,
        )

        results = []
        for r in rows:
            results.append({
                "post_id": str(r["id"]),
                "title": r["title"],
                "url": r["url"],
                "similarity_score": round(1.0 - float(r["distance"]), 3),
                "distance": round(float(r["distance"]), 3),
                "word_count": r["word_count"],
                "source": "embedding",
            })
        return results

    async def _find_by_keyword(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        keyword: str,
    ) -> list[dict]:
        """Find existing posts ranking for a target keyword in GSC data."""
        rows = await db.fetch(
            """
            SELECT DISTINCT p.id, p.title, p.url, p.word_count,
                   AVG(g.avg_position) AS avg_pos,
                   SUM(g.clicks) AS total_clicks
            FROM gsc_metrics g
            JOIN posts p ON p.id = g.post_id
            WHERE p.site_id = $1 AND g.query ILIKE $2
            GROUP BY p.id, p.title, p.url, p.word_count
            ORDER BY total_clicks DESC
            LIMIT 20
            """,
            site_id, f"%{keyword}%",
        )

        results = []
        for r in rows:
            results.append({
                "post_id": str(r["id"]),
                "title": r["title"],
                "url": r["url"],
                "avg_position": round(float(r["avg_pos"]), 1) if r["avg_pos"] else None,
                "total_clicks": r["total_clicks"],
                "word_count": r["word_count"],
                "source": "keyword",
            })
        return results

    def _merge_similar(
        self,
        embedding_results: list[dict],
        keyword_results: list[dict],
    ) -> list[dict]:
        """Merge and deduplicate results from embedding and keyword searches."""
        seen: dict[str, dict] = {}
        for r in embedding_results:
            seen[r["post_id"]] = r
        for r in keyword_results:
            pid = r["post_id"]
            if pid in seen:
                seen[pid]["source"] = "both"
                seen[pid]["avg_position"] = r.get("avg_position")
                seen[pid]["total_clicks"] = r.get("total_clicks")
            else:
                seen[pid] = r
        return list(seen.values())

    async def _get_cluster_context(
        self,
        db: asyncpg.Connection,
        similar_posts: list[dict],
    ) -> str | None:
        """Determine the cluster ecosystem state for similar posts."""
        if not similar_posts:
            return None

        from uuid import UUID as _UUID
        post_id = _UUID(similar_posts[0]["post_id"])
        row = await db.fetchrow(
            """
            SELECT c.ecosystem_state
            FROM post_clusters pc
            JOIN clusters c ON c.id = pc.cluster_id
            WHERE pc.post_id = $1
            LIMIT 1
            """,
            post_id,
        )
        return row["ecosystem_state"] if row else None

    async def _generate_verdict(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        draft_text: str | None,
        target_keyword: str | None,
        similar_posts: list[dict],
        cluster_state: str | None,
    ) -> dict:
        """Generate a structured verdict using Claude API."""
        # Build context
        similar_summary = ""
        very_similar_count = 0
        for sp in similar_posts:
            dist = sp.get("distance")
            if dist is not None and dist < SIMILARITY_THRESHOLD:
                very_similar_count += 1
            pos_info = f", avg position: {sp.get('avg_position', 'N/A')}" if sp.get("avg_position") else ""
            sim_info = f", similarity: {sp.get('similarity_score', 'N/A')}" if sp.get("similarity_score") else ""
            similar_summary += f"- {sp['title']} ({sp['url']}){sim_info}{pos_info}\n"

        draft_snippet = truncate_for_api(draft_text, max_chars=4000, label="oracle_verdict") if draft_text else "N/A"
        keyword_info = target_keyword or "N/A"

        # Fetch cluster context (post count + cannibalization pairs)
        cluster_post_count = 0
        cluster_cann_count = 0
        cluster_id = None
        if similar_posts:
            from uuid import UUID as _UUID
            first_post_id = _UUID(similar_posts[0]["post_id"])
            cluster_row = await db.fetchrow(
                """
                SELECT pc.cluster_id, c.post_count
                FROM post_clusters pc
                JOIN clusters c ON c.id = pc.cluster_id
                WHERE pc.post_id = $1
                LIMIT 1
                """,
                first_post_id,
            )
            if cluster_row:
                cluster_id = cluster_row["cluster_id"]
                cluster_post_count = cluster_row["post_count"] or 0
                cann_row = await db.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM cannibalization_pairs WHERE cluster_id = $1",
                    cluster_id,
                )
                cluster_cann_count = cann_row["cnt"] if cann_row else 0

        # Check GSC for existing top-5 ranking post
        gsc_note = ""
        if target_keyword:
            gsc_row = await db.fetchrow(
                """
                SELECT gm.avg_position, p.title, p.url
                FROM gsc_metrics gm
                JOIN posts p ON p.id = gm.post_id
                WHERE p.site_id = $1 AND gm.query ILIKE $2 AND gm.avg_position <= 5
                ORDER BY gm.avg_position LIMIT 1
                """,
                site_id, f"%{target_keyword}%",
            )
            if gsc_row:
                gsc_note = (
                    f'GSC DATA: An existing post already ranks at position {gsc_row["avg_position"]:.1f} '
                    f'for "{target_keyword}". Strongly consider updating it instead of publishing new content.\n'
                )

        prompt = f"""You are a content ecosystem analyst. Assess whether this new content should \
be published, should update an existing post, or should be skipped entirely.

NEW CONTENT:
Target keyword: {keyword_info}
Draft excerpt: {draft_snippet}

EXISTING SIMILAR POSTS ({len(similar_posts)} found):
{similar_summary or "(none)"}

CLUSTER STATE: {cluster_state or "unknown"}
CLUSTER CONTEXT: This cluster has {cluster_post_count} total posts and {cluster_cann_count} cannibalization pairs.
{gsc_note}VERY SIMILAR POSTS (cosine distance < 0.5): {very_similar_count}

Analyze and provide your assessment. Consider:
1. Is there significant topic overlap with existing content?
2. Would publishing create cannibalization?
3. Is the cluster already saturated (swamp)?
4. Could an existing post be updated instead?

Reply in this exact JSON format:
{{
  "confidence": "high" | "medium" | "low",
  "verdict": "publish" | "update_existing" | "skip",
  "reasoning": "Your detailed analysis...",
  "recommendation": "Specific action to take..."
}}"""

        await self.rate_limiter.wait()
        try:
            response = await self.anthropic.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Parse JSON from Claude response
            verdict = self._parse_json_response(raw)
        except Exception as e:
            logger.error("Claude oracle verdict failed: %s", e)
            verdict = {
                "confidence": "low",
                # Conservative default: do NOT auto-approve when AI is unavailable.
                # Returning "publish" on failure would create cannibalization silently.
                "verdict": "review",
                "reasoning": f"AI analysis unavailable — please review manually before publishing. Error: {e}",
                "recommendation": "Manual review required — check for existing similar posts before publishing.",
            }
            response = None

        if response:
            await log_llm_usage(
                db, site_id=site_id, service="oracle_verdict",
                model=CLAUDE_MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

        # Build final response
        return {
            "confidence": verdict.get("confidence", "low"),
            "verdict": verdict.get("verdict", "review"),
            "reasoning": verdict.get("reasoning", ""),
            "similar_posts": similar_posts,
            "cluster_state": cluster_state,
            "recommendation": verdict.get("recommendation", ""),
        }

    @staticmethod
    def _parse_json_response(raw: str) -> dict:
        """Parse JSON from Claude response, handling markdown code blocks."""
        import json

        # Strip markdown code blocks if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (``` markers)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {
                "confidence": "low",
                "verdict": "review",
                "reasoning": raw,
                "recommendation": "Manual review recommended — AI response was not structured.",
            }
