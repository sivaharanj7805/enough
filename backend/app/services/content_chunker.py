"""Content chunker — splits posts into semantic chunks by heading structure.

Splits blog posts into meaningful sections based on H2/H3 headings.
Each chunk gets embedded separately for fine-grained cannibalization
detection. A 3000-word guide covering 5 subtopics becomes 5+ chunks,
each compared independently against every other chunk in the cluster.

Chunking strategy:
1. Primary split: H2 headings (major sections)
2. Secondary split: H3 headings within large H2 sections
3. Fallback: sliding window of ~300 words with 50-word overlap
4. Minimum chunk size: 50 words (skip tiny fragments)
5. Maximum chunk size: 500 words (split oversized sections)
6. Intro section (before first heading) treated as its own chunk

The heading text is preserved as metadata — used in cannibalization
reports to tell users exactly WHICH section is cannibalizing.
"""

import logging
import re
from dataclasses import dataclass, field
from uuid import UUID

import asyncpg
from openai import AsyncOpenAI

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Chunking parameters
MIN_CHUNK_WORDS = 50       # Skip chunks smaller than this
MAX_CHUNK_WORDS = 500      # Split chunks larger than this
SLIDING_WINDOW_WORDS = 300 # Fallback window size
SLIDING_OVERLAP_WORDS = 50 # Overlap between sliding windows
CANNIBAL_THRESHOLD = 0.85  # Chunk-pair similarity threshold


@dataclass
class ContentChunk:
    """A single chunk of a post's content."""
    chunk_index: int
    heading: str | None          # H2/H3 text, None for intro
    heading_level: int | None    # 2 or 3, None for intro
    body_text: str
    word_count: int
    start_char: int
    end_char: int


@dataclass
class ChunkPair:
    """A pair of chunks from different posts with high similarity."""
    post_a_id: UUID
    post_b_id: UUID
    chunk_a_index: int
    chunk_b_index: int
    chunk_a_heading: str | None
    chunk_b_heading: str | None
    similarity: float


def split_into_chunks(body_text: str) -> list[ContentChunk]:
    """Split post body text into semantic chunks by heading structure.

    Strategy:
    1. Split on H2 headings first (## in markdown, or <h2> in HTML)
    2. If any section > MAX_CHUNK_WORDS, split on H3 within it
    3. If still > MAX_CHUNK_WORDS, use sliding window
    4. Drop chunks < MIN_CHUNK_WORDS
    5. Preserve intro (text before first heading) as chunk 0
    """
    if not body_text or not body_text.strip():
        return []

    # Normalize: handle both markdown and HTML headings
    text = body_text.strip()

    # Split on H2 headings (markdown ## or HTML <h2>)
    # Pattern matches: ## Heading, <h2>Heading</h2>, <h2 class="...">Heading</h2>
    h2_pattern = re.compile(
        r'(?:^|\n)(?:#{2}\s+(.+?)(?:\n|$))|(?:<h2[^>]*>(.+?)</h2>)',
        re.IGNORECASE | re.MULTILINE,
    )

    h3_pattern = re.compile(
        r'(?:^|\n)(?:#{3}\s+(.+?)(?:\n|$))|(?:<h3[^>]*>(.+?)</h3>)',
        re.IGNORECASE | re.MULTILINE,
    )

    # Find all H2 positions
    h2_matches = list(h2_pattern.finditer(text))

    if not h2_matches:
        # No headings found — use sliding window
        return _sliding_window_chunks(text, 0)

    raw_sections: list[tuple[str | None, int | None, str, int]] = []

    # Intro section (before first H2)
    intro_start = 0
    intro_end = h2_matches[0].start()
    intro_text = text[intro_start:intro_end].strip()
    if intro_text:
        raw_sections.append((None, None, intro_text, intro_start))

    # H2 sections
    for i, match in enumerate(h2_matches):
        heading = match.group(1) or match.group(2) or ""
        heading = heading.strip()
        section_start = match.end()
        section_end = h2_matches[i + 1].start() if i + 1 < len(h2_matches) else len(text)
        section_text = text[section_start:section_end].strip()
        if section_text:
            raw_sections.append((heading, 2, section_text, section_start))

    # Process each raw section — split large ones by H3 or sliding window
    chunks: list[ContentChunk] = []
    chunk_index = 0

    for heading, level, section_text, section_start in raw_sections:
        word_count = len(section_text.split())

        if word_count <= MAX_CHUNK_WORDS:
            # Section is small enough — keep as-is
            if word_count >= MIN_CHUNK_WORDS:
                chunks.append(ContentChunk(
                    chunk_index=chunk_index,
                    heading=heading,
                    heading_level=level,
                    body_text=section_text,
                    word_count=word_count,
                    start_char=section_start,
                    end_char=section_start + len(section_text),
                ))
                chunk_index += 1
        else:
            # Try splitting by H3
            h3_matches = list(h3_pattern.finditer(section_text))
            if h3_matches:
                sub_sections = _split_by_subheadings(
                    section_text, h3_matches, heading, section_start,
                )
                for sub_heading, sub_level, sub_text, sub_start in sub_sections:
                    sub_wc = len(sub_text.split())
                    if sub_wc < MIN_CHUNK_WORDS:
                        continue
                    if sub_wc > MAX_CHUNK_WORDS:
                        # Still too big — sliding window
                        for sw_chunk in _sliding_window_chunks(sub_text, sub_start):
                            sw_chunk.chunk_index = chunk_index
                            sw_chunk.heading = sub_heading
                            sw_chunk.heading_level = sub_level
                            chunks.append(sw_chunk)
                            chunk_index += 1
                    else:
                        chunks.append(ContentChunk(
                            chunk_index=chunk_index,
                            heading=sub_heading,
                            heading_level=sub_level,
                            body_text=sub_text,
                            word_count=sub_wc,
                            start_char=sub_start,
                            end_char=sub_start + len(sub_text),
                        ))
                        chunk_index += 1
            else:
                # No H3s — sliding window
                for sw_chunk in _sliding_window_chunks(section_text, section_start):
                    sw_chunk.chunk_index = chunk_index
                    sw_chunk.heading = heading
                    sw_chunk.heading_level = level
                    chunks.append(sw_chunk)
                    chunk_index += 1

    return chunks


def _split_by_subheadings(
    text: str,
    matches: list[re.Match],
    parent_heading: str | None,
    base_offset: int,
) -> list[tuple[str | None, int | None, str, int]]:
    """Split a section by H3 matches."""
    sections = []

    # Text before first H3
    pre_text = text[:matches[0].start()].strip()
    if pre_text:
        sections.append((parent_heading, 2, pre_text, base_offset))

    for i, match in enumerate(matches):
        h3_heading = match.group(1) or match.group(2) or ""
        h3_heading = h3_heading.strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sub_text = text[start:end].strip()
        if sub_text:
            sections.append((h3_heading, 3, sub_text, base_offset + start))

    return sections


def _sliding_window_chunks(
    text: str,
    base_offset: int,
) -> list[ContentChunk]:
    """Split text into overlapping sliding window chunks."""
    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return []

    chunks = []
    chunk_index = 0
    pos = 0

    while pos < len(words):
        end = min(pos + SLIDING_WINDOW_WORDS, len(words))
        chunk_words = words[pos:end]
        chunk_text = " ".join(chunk_words)

        if len(chunk_words) >= MIN_CHUNK_WORDS:
            # Approximate character offsets
            char_start = base_offset + len(" ".join(words[:pos])) + (1 if pos > 0 else 0)
            char_end = char_start + len(chunk_text)

            chunks.append(ContentChunk(
                chunk_index=chunk_index,
                heading=None,
                heading_level=None,
                body_text=chunk_text,
                word_count=len(chunk_words),
                start_char=char_start,
                end_char=char_end,
            ))
            chunk_index += 1

        if end >= len(words):
            break
        pos += SLIDING_WINDOW_WORDS - SLIDING_OVERLAP_WORDS

    return chunks


class ContentChunkerService:
    """Chunks posts, embeds chunks, detects chunk-level cannibalization."""

    def __init__(self) -> None:
        settings = get_settings()
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def chunk_post(
        self,
        db: asyncpg.Connection,
        post_id: UUID,
        site_id: UUID,
        body_text: str,
    ) -> int:
        """Split a post into chunks and store them.

        Returns number of chunks created.
        """
        # Clear existing chunks for this post
        await db.execute(
            "DELETE FROM content_chunks WHERE post_id = $1", post_id,
        )

        chunks = split_into_chunks(body_text)
        if not chunks:
            return 0

        for chunk in chunks:
            await db.execute(
                """
                INSERT INTO content_chunks
                    (post_id, site_id, chunk_index, heading, heading_level,
                     body_text, word_count, start_char, end_char)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                post_id, site_id, chunk.chunk_index,
                chunk.heading, chunk.heading_level,
                chunk.body_text, chunk.word_count,
                chunk.start_char, chunk.end_char,
            )

        logger.info("Chunked post %s into %d chunks", post_id, len(chunks))
        return len(chunks)

    async def chunk_site(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> int:
        """Chunk all posts for a site. Returns total chunks created."""
        posts = await db.fetch(
            """
            SELECT id, body_text FROM posts
            WHERE site_id = $1
              AND body_text IS NOT NULL
              AND LENGTH(body_text) > 200
            """,
            site_id,
        )

        total = 0
        for post in posts:
            count = await self.chunk_post(
                db, post["id"], site_id, post["body_text"],
            )
            total += count

        logger.info("Chunked %d posts into %d total chunks for site %s",
                     len(posts), total, site_id)
        return total

    async def embed_chunks(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> int:
        """Embed all un-embedded chunks for a site.

        Returns number of chunks embedded.
        """
        chunks = await db.fetch(
            """
            SELECT cc.id AS chunk_id, cc.post_id, cc.heading, cc.body_text
            FROM content_chunks cc
            LEFT JOIN chunk_embeddings ce ON ce.chunk_id = cc.id
            WHERE cc.site_id = $1
              AND ce.id IS NULL
            ORDER BY cc.post_id, cc.chunk_index
            """,
            site_id,
        )

        if not chunks:
            return 0

        embedded = 0
        batch_size = 20

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = []
            for c in batch:
                # Prepend heading for better topical embedding
                heading = c["heading"] or ""
                body = c["body_text"][:2000]
                if heading:
                    texts.append(f"{heading}. {heading}. {body}")
                else:
                    texts.append(body)

            await self.rate_limiter.wait()
            try:
                response = await self.openai.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                for j, emb_data in enumerate(response.data):
                    chunk = batch[j]
                    await db.execute(
                        """
                        INSERT INTO chunk_embeddings (chunk_id, post_id, embedding)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            embedding = $3, created_at = NOW()
                        """,
                        chunk["chunk_id"], chunk["post_id"],
                        str(emb_data.embedding),
                    )
                    embedded += 1
            except Exception as e:
                logger.error("Chunk embedding batch failed: %s", e)

        logger.info("Embedded %d chunks for site %s", embedded, site_id)
        return embedded

    async def detect_chunk_cannibalization(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        threshold: float = CANNIBAL_THRESHOLD,
    ) -> int:
        """Detect chunk-level cannibalization within clusters.

        For each pair of posts in the same cluster, compare all chunk
        pairs. If ANY chunk pair exceeds the threshold, flag it.

        Returns number of chunk-level cannibalizations found.
        """
        # Clear old results
        await db.execute(
            "DELETE FROM chunk_cannibalization WHERE site_id = $1", site_id,
        )

        # Get all clusters for this site
        clusters = await db.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id,
        )

        total_found = 0

        for cluster in clusters:
            # Get all posts in this cluster that have chunk embeddings
            posts_in_cluster = await db.fetch(
                """
                SELECT DISTINCT ce.post_id
                FROM post_clusters pc
                JOIN chunk_embeddings ce ON ce.post_id = pc.post_id
                WHERE pc.cluster_id = $1
                """,
                cluster["id"],
            )

            post_ids = [p["post_id"] for p in posts_in_cluster]
            if len(post_ids) < 2:
                continue

            # Compare each pair of posts
            for i in range(len(post_ids)):
                for j in range(i + 1, len(post_ids)):
                    post_a = post_ids[i]
                    post_b = post_ids[j]

                    # Find highest similarity chunk pair between these two posts
                    # Uses HNSW index for efficient search
                    best_pair = await db.fetchrow(
                        """
                        SELECT
                            ca.chunk_id AS chunk_a_id,
                            cb.chunk_id AS chunk_b_id,
                            cca.heading AS chunk_a_heading,
                            ccb.heading AS chunk_b_heading,
                            1 - (ca.embedding <=> cb.embedding) AS similarity
                        FROM chunk_embeddings ca
                        JOIN chunk_embeddings cb ON cb.post_id = $2
                        JOIN content_chunks cca ON cca.id = ca.chunk_id
                        JOIN content_chunks ccb ON ccb.id = cb.chunk_id
                        WHERE ca.post_id = $1
                        ORDER BY ca.embedding <=> cb.embedding
                        LIMIT 1
                        """,
                        post_a, post_b,
                    )

                    if not best_pair:
                        continue

                    sim = float(best_pair["similarity"])
                    if sim >= threshold:
                        await db.execute(
                            """
                            INSERT INTO chunk_cannibalization
                                (site_id, post_a_id, post_b_id,
                                 chunk_a_id, chunk_b_id, similarity,
                                 chunk_a_heading, chunk_b_heading)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            """,
                            site_id, post_a, post_b,
                            best_pair["chunk_a_id"],
                            best_pair["chunk_b_id"],
                            sim,
                            best_pair["chunk_a_heading"],
                            best_pair["chunk_b_heading"],
                        )
                        total_found += 1

                        logger.info(
                            "Chunk cannibalization: '%s' ↔ '%s' (sim=%.3f)",
                            best_pair["chunk_a_heading"] or "intro",
                            best_pair["chunk_b_heading"] or "intro",
                            sim,
                        )

        logger.info("Found %d chunk-level cannibalizations for site %s",
                     total_found, site_id)
        return total_found
