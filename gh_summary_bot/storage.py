import logging

import aiopg

logger = logging.getLogger(__name__)


class PostgreSQLUserStorage:
    def __init__(self, pool: aiopg.Pool) -> None:
        self._pool = pool

    async def store_user(self, telegram_id: int, github_username: str | None = None) -> None:
        """Store telegram user association."""
        query = """
        INSERT INTO telegram_users (telegram_id, github_username, last_query)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (telegram_id) DO UPDATE SET
            github_username = COALESCE(
                EXCLUDED.github_username,
                telegram_users.github_username
            ),
            last_query = CURRENT_TIMESTAMP
        """

        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(query, (telegram_id, github_username))


class DatabaseInitializer:
    def __init__(self, pool: aiopg.Pool) -> None:
        self._pool = pool

    async def initialize_tables(self) -> None:
        """Create necessary database tables."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS telegram_users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            github_username VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_query TIMESTAMP
        );
        """

        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(create_table_query)
