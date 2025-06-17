"""Database operations for PostgreSQL using aiopg."""

import json
from dataclasses import asdict
from typing import Dict, Optional

import aiopg

from .models import ContributionStats


class DatabaseManager:
    """Handles PostgreSQL database operations"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None

    async def initialize(self):
        """Initialize connection pool and create tables"""
        self.pool = await aiopg.create_pool(self.database_url)
        await self._create_tables()

    async def close(self):
        """Close connection pool"""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    async def _create_tables(self):
        """Create necessary database tables"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS contribution_reports (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            year INTEGER NOT NULL,
            total_commits INTEGER DEFAULT 0,
            total_prs INTEGER DEFAULT 0,
            total_issues INTEGER DEFAULT 0,
            total_discussions INTEGER DEFAULT 0,
            total_reviews INTEGER DEFAULT 0,
            repositories_contributed INTEGER DEFAULT 0,
            languages JSONB DEFAULT '{}',
            starred_repos INTEGER DEFAULT 0,
            followers INTEGER DEFAULT 0,
            following INTEGER DEFAULT 0,
            public_repos INTEGER DEFAULT 0,
            private_contributions INTEGER DEFAULT 0,
            lines_added INTEGER DEFAULT 0,
            lines_deleted INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(username, year)
        );
        
        CREATE TABLE IF NOT EXISTS telegram_users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            github_username VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_query TIMESTAMP
        );
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(create_table_query)

    async def save_report(self, stats: ContributionStats) -> int:
        """Save or update contribution report"""
        insert_query = """
        INSERT INTO contribution_reports (
            username, year, total_commits, total_prs, total_issues,
            total_discussions, total_reviews, repositories_contributed,
            languages, starred_repos, followers, following, public_repos,
            private_contributions, lines_added, lines_deleted
        ) VALUES (
            %(username)s, %(year)s, %(total_commits)s, %(total_prs)s,
            %(total_issues)s, %(total_discussions)s, %(total_reviews)s,
            %(repositories_contributed)s, %(languages)s, %(starred_repos)s,
            %(followers)s, %(following)s, %(public_repos)s,
            %(private_contributions)s, %(lines_added)s, %(lines_deleted)s
        )
        ON CONFLICT (username, year) DO UPDATE SET
            total_commits = EXCLUDED.total_commits,
            total_prs = EXCLUDED.total_prs,
            total_issues = EXCLUDED.total_issues,
            total_discussions = EXCLUDED.total_discussions,
            total_reviews = EXCLUDED.total_reviews,
            repositories_contributed = EXCLUDED.repositories_contributed,
            languages = EXCLUDED.languages,
            starred_repos = EXCLUDED.starred_repos,
            followers = EXCLUDED.followers,
            following = EXCLUDED.following,
            public_repos = EXCLUDED.public_repos,
            private_contributions = EXCLUDED.private_contributions,
            lines_added = EXCLUDED.lines_added,
            lines_deleted = EXCLUDED.lines_deleted,
            created_at = CURRENT_TIMESTAMP
        RETURNING id;
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                data = asdict(stats)
                data["languages"] = json.dumps(data["languages"])
                await cur.execute(insert_query, data)
                report_id = (await cur.fetchone())[0]

        return report_id

    async def get_report(self, username: str, year: int) -> Optional[Dict]:
        """Retrieve a contribution report"""
        query = """
        SELECT * FROM contribution_reports
        WHERE username = %s AND year = %s
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (username, year))
                result = await cur.fetchone()

        if result:
            # Convert tuple result to dict
            columns = [
                "id",
                "username",
                "year",
                "total_commits",
                "total_prs",
                "total_issues",
                "total_discussions",
                "total_reviews",
                "repositories_contributed",
                "languages",
                "starred_repos",
                "followers",
                "following",
                "public_repos",
                "private_contributions",
                "lines_added",
                "lines_deleted",
                "created_at",
            ]
            result_dict = dict(zip(columns, result))
            # aiopg returns JSONB fields as Python objects, not JSON strings
            result_dict["languages"] = (
                result_dict["languages"] if result_dict["languages"] else {}
            )
            return result_dict

        return None

    async def save_telegram_user(self, telegram_id: int, github_username: str = None):
        """Save or update Telegram user"""
        query = """
        INSERT INTO telegram_users (telegram_id, github_username, last_query)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (telegram_id) DO UPDATE SET
            github_username = COALESCE(EXCLUDED.github_username, telegram_users.github_username),
            last_query = CURRENT_TIMESTAMP
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (telegram_id, github_username))