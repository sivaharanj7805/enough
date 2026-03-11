"""OpenAI embedding pipeline.

Generates text-embedding-3-small vectors for post content,
with change detection via content_hash and batch processing.

Uses pgvector's bracket format [x,y,z] for reliable vector serialization.
"""

import json
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
            SELECT p.id, p.body_text, p.content_hash
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

        logger.info("Embeddings: %d posts need embedding for site %s", len(rows), site_id)
        total_generated = 0

        # Process in batches
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            texts = [self._prepare_text(row["body_text"]) for row in batch]

            await self.rate_limiter.wait()

            try:
                response = await self.client.embeddings.create(
                    model=MODEL,
                    input=texts,
                    dimensions=DIMENSIONS,
                )
            except Exception as e:
                logger.error("OpenAI embedding API error: %s", e)
                # Try individual texts in case one is problematic
                for j, row in enumerate(batch):
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
                i + 1, min(i + BATCH_SIZE, len(rows)), total_generated,
            )

        logger.info(
            "Embeddings: generated %d embeddings for site %s",
            total_generated, site_id,
        )
        return total_generated

    async def _generate_single(self, db: asyncpg.Connection, row: asyncpg.Record) -> None:
        """Generate embedding for a single post (fallback for batch failures)."""
        text = self._prepare_text(row["body_text"])

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

    def _prepare_text(self, text: str) -> str:
        """Truncate text to fit within token limits."""
        if len(text) > TRUNCATE_CHARS:
            text = text[:TRUNCATE_CHARS]
        return text.strip()
