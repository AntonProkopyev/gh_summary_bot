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
        
        CREATE TABLE IF NOT EXISTS user_pull_requests (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            pr_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            additions INTEGER DEFAULT 0,
            deletions INTEGER DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(username, pr_id)
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

    async def get_all_time_stats(self, username: str) -> Optional[Dict]:
        """Aggregate all-time statistics for a user across all years"""
        # First get cumulative stats
        cumulative_query = """
        SELECT 
            username,
            COUNT(*) as total_years,
            SUM(total_commits) as total_commits,
            SUM(total_prs) as total_prs,
            SUM(total_issues) as total_issues,
            SUM(total_discussions) as total_discussions,
            SUM(total_reviews) as total_reviews,
            SUM(private_contributions) as private_contributions,
            SUM(lines_added) as lines_added,
            SUM(lines_deleted) as lines_deleted,
            MIN(year) as first_year,
            MAX(year) as last_year,
            MAX(created_at) as last_updated
        FROM contribution_reports 
        WHERE username = %s
        GROUP BY username
        """

        # Get latest snapshot values from the most recent year
        snapshot_query = """
        SELECT 
            repositories_contributed,
            starred_repos, 
            followers, 
            following, 
            public_repos
        FROM contribution_reports 
        WHERE username = %s 
        ORDER BY year DESC 
        LIMIT 1
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Get cumulative stats
                await cur.execute(cumulative_query, (username,))
                cumulative_result = await cur.fetchone()

                if not cumulative_result:
                    return None

                # Get snapshot stats from latest year
                await cur.execute(snapshot_query, (username,))
                snapshot_result = await cur.fetchone()

        if cumulative_result and snapshot_result:
            cumulative_columns = [
                "username",
                "total_years",
                "total_commits",
                "total_prs",
                "total_issues",
                "total_discussions",
                "total_reviews",
                "private_contributions",
                "lines_added",
                "lines_deleted",
                "first_year",
                "last_year",
                "last_updated",
            ]
            result_dict = dict(zip(cumulative_columns, cumulative_result))

            snapshot_columns = [
                "repositories_contributed",
                "starred_repos",
                "followers",
                "following",
                "public_repos",
            ]
            snapshot_dict = dict(zip(snapshot_columns, snapshot_result))
            result_dict.update(snapshot_dict)

            # Get aggregated language statistics
            lang_query = """
            SELECT jsonb_object_agg(lang, total_commits) as languages
            FROM (
                SELECT lang, SUM(commits::integer) as total_commits
                FROM contribution_reports cr,
                     jsonb_each_text(cr.languages) AS lang_data(lang, commits)
                WHERE cr.username = %s
                GROUP BY lang
                ORDER BY total_commits DESC
            ) lang_stats
            """

            async with conn.cursor() as cur:
                await cur.execute(lang_query, (username,))
                lang_result = await cur.fetchone()
                result_dict["languages"] = (
                    lang_result[0] if lang_result and lang_result[0] else {}
                )

            return result_dict

        return None

    async def get_existing_years(self, username: str) -> list:
        """Get list of years that already have reports for a user"""
        query = """
        SELECT year FROM contribution_reports 
        WHERE username = %s 
        ORDER BY year
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (username,))
                results = await cur.fetchall()
                return [row[0] for row in results] if results else []

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

    async def get_cached_prs(self, username: str) -> list:
        """Get cached pull requests for a user"""
        query = """
        SELECT pr_id, created_at, additions, deletions 
        FROM user_pull_requests 
        WHERE username = %s
        ORDER BY created_at DESC
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (username,))
                results = await cur.fetchall()
                return (
                    [
                        {
                            "pr_id": row[0],
                            "createdAt": row[1].isoformat() + "Z",
                            "additions": row[2],
                            "deletions": row[3],
                        }
                        for row in results
                    ]
                    if results
                    else []
                )

    async def cache_prs(self, username: str, prs: list):
        """Cache pull requests for a user"""
        if not prs:
            return

        insert_query = """
        INSERT INTO user_pull_requests (username, pr_id, created_at, additions, deletions)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (username, pr_id) DO UPDATE SET
            additions = EXCLUDED.additions,
            deletions = EXCLUDED.deletions,
            fetched_at = CURRENT_TIMESTAMP
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                for pr in prs:
                    # Extract PR ID from node_id or create one from createdAt + additions
                    pr_id = f"{pr['createdAt']}_{pr['additions']}_{pr['deletions']}"
                    await cur.execute(
                        insert_query,
                        (
                            username,
                            pr_id,
                            pr["createdAt"].replace(
                                "Z", "+00:00"
                            ),  # Convert to proper timestamp
                            pr["additions"],
                            pr["deletions"],
                        ),
                    )

    async def has_pr_cache(self, username: str) -> bool:
        """Check if user has cached PR data"""
        query = """
        SELECT COUNT(*) FROM user_pull_requests 
        WHERE username = %s
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, (username,))
                count = (await cur.fetchone())[0]
                return count > 0
