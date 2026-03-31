"""OpenAI embedding pipeline.

Generates text-embedding-3-small vectors for post content,
with change detection via content_hash and batch processing.

Uses pgvector's bracket format [x,y,z] for reliable vector serialization.
"""

import logging
from uuid import UUID

import asyncpg
from openai import AsyncOpenAI

from app.config import get_settings
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# OpenAI text-embedding-3-small limits
MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
MAX_TOKENS_PER_TEXT = 8191  # Model max
TRUNCATE_CHARS = 20000  # ~5000 tokens, safe truncation
BATCH_SIZE = 100  # Max texts per API call


def _vector_to_pgvector(vector: list[float]) -> str:
    """Convert a list of floats to pgvector's bracket format: [x,y,z,...]"""
    return "[" + ",".join(str(v) for v in vector) + "]"


class EmbeddingPipeline:
    """Generate and store embeddings for posts using OpenAI."""

    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def generate_for_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Generate embeddings for all posts in a site that need them.

        Skips posts whose content_hash matches the existing embedding.
        Returns the number of embeddings generated.
        """
        # Fetch posts that need embedding (new or changed content)
        rows = await db.fetch(
            """
            SELECT p.id, p.title, p.body_text, p.content_hash
            FROM posts p
            LEFT JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE p.site_id = $1
              AND p.body_text IS NOT NULL
              AND p.body_text != ''
              AND (pe.id IS NULL OR pe.content_hash != p.content_hash)
            """,
            site_id,
        )

        if not rows:
            logger.info("Embeddings: all posts up-to-date for site %s", site_id)
            return 0

        # Split posts into short (single-text, batchable) and long (multi-chunk)
        short_rows = []
        long_rows = []
        for row in rows:
            text = f"{row['title'] or ''}\n\n{row['body_text']}"
            if len(text) <= TRUNCATE_CHARS:
                short_rows.append(row)
            else:
                long_rows.append(row)

        if long_rows:
            logger.info(
                "Embeddings: %d short posts (batchable) + %d long posts (chunked)",
                len(short_rows), len(long_rows),
            )

        total_generated = 0

        # ── Batch process short posts (single text each, 100 per API call) ──
        for i in range(0, len(short_rows), BATCH_SIZE):
            batch = short_rows[i : i + BATCH_SIZE]
            texts = [self._prepare_text(row["title"], row["body_text"]) for row in batch]

            await self.rate_limiter.wait()

            try:
                response = await self.client.embeddings.create(
                    model=MODEL,
                    input=texts,
                    dimensions=DIMENSIONS,
                )
            except Exception as e:
                logger.error("OpenAI embedding API error: %s", e)
                for _j, row in enumerate(batch):
                    await self._generate_single(db, row)
                    total_generated += 1
                continue

            for j, embedding_data in enumerate(response.data):
                row = batch[j]
                vector = embedding_data.embedding

                try:
                    await db.execute(
                        """
                        INSERT INTO post_embeddings (post_id, embedding, model, content_hash)
                        VALUES ($1, $2::vector, $3, $4)
                        ON CONFLICT (post_id) DO UPDATE SET
                            embedding = EXCLUDED.embedding,
                            content_hash = EXCLUDED.content_hash,
                            updated_at = NOW()
                        """,
                        row["id"],
                        _vector_to_pgvector(vector),
                        MODEL,
                        row["content_hash"],
                    )
                    total_generated += 1
                except Exception as e:
                    logger.error("Failed to store embedding for post %s: %s", row["id"], e)

            logger.info(
                "Embeddings: processed batch %d-%d (%d total)",
                i + 1, min(i + BATCH_SIZE, len(short_rows)), total_generated,
            )

        # ── Process long posts individually with chunked mean-pooling ──
        for row in long_rows:
            chunks = self._prepare_text_chunked(row["title"], row["body_text"])
            try:
                chunk_vectors: list[list[float]] = []
                for chunk in chunks:
                    await self.rate_limiter.wait()
                    response = await self.client.embeddings.create(
                        model=MODEL,
                        input=[chunk],
                        dimensions=DIMENSIONS,
                    )
                    chunk_vectors.append(response.data[0].embedding)

                # Mean-pool all chunk vectors into one post embedding
                vector = self._mean_vector(chunk_vectors)

                await db.execute(
                    """
                    INSERT INTO post_embeddings (post_id, embedding, model, content_hash)
                    VALUES ($1, $2::vector, $3, $4)
                    ON CONFLICT (post_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = NOW()
                    """,
                    row["id"],
                    _vector_to_pgvector(vector),
                    MODEL,
                    row["content_hash"],
                )
                total_generated += 1
                logger.info(
                    "Embeddings: chunked %d chunks for long post %s",
                    len(chunks), row["id"],
                )
            except Exception as e:
                logger.error("Failed to generate chunked embedding for post %s: %s", row["id"], e)

        logger.info(
            "Embeddings: generated %d embeddings for site %s",
            total_generated, site_id,
        )
        return total_generated

    async def _generate_single(self, db: asyncpg.Connection, row: asyncpg.Record) -> None:
        """Generate embedding for a single post (fallback for batch failures)."""
        text = self._prepare_text(row.get("title"), row["body_text"])

        try:
            await self.rate_limiter.wait()
            response = await self.client.embeddings.create(
                model=MODEL,
                input=[text],
                dimensions=DIMENSIONS,
            )
            vector = response.data[0].embedding

            await db.execute(
                """
                INSERT INTO post_embeddings (post_id, embedding, model, content_hash)
                VALUES ($1, $2::vector, $3, $4)
                ON CONFLICT (post_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = NOW()
                """,
                row["id"],
                _vector_to_pgvector(vector),
                MODEL,
                row["content_hash"],
            )
        except Exception as e:
            logger.error("Failed to generate single embedding for post %s: %s", row["id"], e)

    def _prepare_text(self, title: str | None, body: str) -> str:
        """Prepend title to body and truncate to fit within token limits.

        Title prepending improves semantic retrieval quality by ensuring
        the dense keyword signal in the title is captured in the embedding.
        """
        text = f"{title}\n\n{body}" if title else body
        if len(text) > TRUNCATE_CHARS:
            text = text[:TRUNCATE_CHARS]
        return text.strip()

    def _prepare_text_chunked(self, title: str | None, body: str) -> list[str]:
        """Split long texts into TRUNCATE_CHARS chunks for mean-pooled embedding.

        For posts under the limit, returns a single-element list (same as _prepare_text).
        For posts over the limit, splits into overlapping chunks with title prepended
        to each chunk so every chunk captures the topic context.

        Returns list of text chunks to embed separately (then average the vectors).
        """
        text = f"{title}\n\n{body}" if title else body
        if len(text) <= TRUNCATE_CHARS:
            return [text.strip()]

        # Split into chunks with 500-char overlap for context continuity
        overlap = 500
        title_prefix = f"{title}\n\n" if title else ""
        # Reserve space for title in each chunk
        chunk_size = TRUNCATE_CHARS - len(title_prefix)
        chunks: list[str] = []
        start = len(title_prefix)  # Skip past title in first chunk
        full_text = text

        # First chunk includes the original title+body start
        chunks.append(full_text[:TRUNCATE_CHARS].strip())

        # Subsequent chunks: title + body segment
        start = TRUNCATE_CHARS - overlap
        while start < len(full_text):
            chunk_body = full_text[start:start + chunk_size]
            if len(chunk_body.strip()) < 200:
                break  # Don't embed tiny tail chunks
            chunks.append(f"{title_prefix}{chunk_body}".strip())
            start += chunk_size - overlap

        return chunks

    @staticmethod
    def _mean_vector(vectors: list[list[float]]) -> list[float]:
        """Average multiple embedding vectors into one."""
        if len(vectors) == 1:
            return vectors[0]
        dims = len(vectors[0])
        mean = [0.0] * dims
        for vec in vectors:
            for i in range(dims):
                mean[i] += vec[i]
        n = len(vectors)
        return [v / n for v in mean]
