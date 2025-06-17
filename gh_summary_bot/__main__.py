#!/usr/bin/env python3
"""
GitHub Contribution Analyzer with PostgreSQL Storage and Telegram Bot Interface

Features:
- Fetches user contributions using GitHub GraphQL API
- Stores reports in PostgreSQL database
- Telegram bot interface for easy access
- Analyzes: commits, PRs, issues, discussions, stars, forks, etc.

Requirements:
pip install python-telegram-bot psycopg2-binary aiohttp python-dotenv
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import asyncio
from dataclasses import dataclass, asdict

import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

from .gh_gql_client import GitHubGraphQLClient, GitHubGraphQLError

# Load environment variables
load_dotenv()

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


@dataclass
class ContributionStats:
    """Data class for GitHub contribution statistics"""

    username: str
    year: int
    total_commits: int
    total_prs: int
    total_issues: int
    total_discussions: int
    total_reviews: int
    repositories_contributed: int
    languages: Dict[str, int]
    starred_repos: int
    followers: int
    following: int
    public_repos: int
    private_contributions: int
    lines_added: int
    lines_deleted: int
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class GitHubAnalyzer:
    """Handles GitHub GraphQL API interactions"""

    def __init__(self, token: str):
        self.token = token
        self.client = GitHubGraphQLClient(token)

    async def get_user_contributions(self, username: str, year: int) -> ContributionStats:
        """Fetch comprehensive user contribution data"""

        # Main user query
        user_query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              totalIssueContributions
              totalPullRequestContributions
              totalPullRequestReviewContributions
              totalRepositoriesWithContributedCommits
              totalRepositoriesWithContributedPullRequests
              totalRepositoriesWithContributedIssues
              restrictedContributionsCount
              commitContributionsByRepository {
                repository {
                  name
                  primaryLanguage { name }
                }
                contributions { totalCount }
              }
            }
            repositories(first: 100, ownerAffiliations: OWNER) {
              totalCount
            }
            starredRepositories { totalCount }
            followers { totalCount }
            following { totalCount }
            pullRequests(first: 100, states: [OPEN, MERGED, CLOSED]) {
              nodes {
                additions
                deletions
              }
            }
            issues(first: 100, states: [OPEN, CLOSED]) {
              totalCount
            }
            repositoryDiscussions(first: 100) {
              totalCount
            }
          }
        }
        """

        from_date = f"{year}-01-01T00:00:00Z"
        to_date = f"{year}-12-31T23:59:59Z"

        variables = {"login": username, "from": from_date, "to": to_date}

        try:
            async with self.client as client:
                data = await client.query(user_query, variables)
                user_data = data["user"]
                contributions = user_data["contributionsCollection"]

            # Calculate language statistics
            languages = {}
            for repo_contrib in contributions["commitContributionsByRepository"]:
                if repo_contrib["repository"]["primaryLanguage"]:
                    lang = repo_contrib["repository"]["primaryLanguage"]["name"]
                    count = repo_contrib["contributions"]["totalCount"]
                    languages[lang] = languages.get(lang, 0) + count

            # Calculate lines of code
            lines_added = 0
            lines_deleted = 0
            for pr in user_data["pullRequests"]["nodes"]:
                lines_added += pr["additions"]
                lines_deleted += pr["deletions"]

            # Get total repositories contributed to
            repos_contributed = (
                contributions["totalRepositoriesWithContributedCommits"]
                + contributions["totalRepositoriesWithContributedPullRequests"]
                + contributions["totalRepositoriesWithContributedIssues"]
            )

            return ContributionStats(
                username=username,
                year=year,
                total_commits=contributions["totalCommitContributions"],
                total_prs=contributions["totalPullRequestContributions"],
                total_issues=contributions["totalIssueContributions"],
                total_discussions=user_data["repositoryDiscussions"]["totalCount"],
                total_reviews=contributions["totalPullRequestReviewContributions"],
                repositories_contributed=repos_contributed,
                languages=languages,
                starred_repos=user_data["starredRepositories"]["totalCount"],
                followers=user_data["followers"]["totalCount"],
                following=user_data["following"]["totalCount"],
                public_repos=user_data["repositories"]["totalCount"],
                private_contributions=contributions["restrictedContributionsCount"],
                lines_added=lines_added,
                lines_deleted=lines_deleted,
            )

        except GitHubGraphQLError as e:
            logger.error(f"Error fetching data for {username}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching data for {username}: {e}")
            raise


class DatabaseManager:
    """Handles PostgreSQL database operations"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._create_tables()

    def _get_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url)

    def _create_tables(self):
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

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_table_query)
            conn.commit()

    def save_report(self, stats: ContributionStats) -> int:
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

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                data = asdict(stats)
                data["languages"] = json.dumps(data["languages"])
                cur.execute(insert_query, data)
                report_id = cur.fetchone()[0]
            conn.commit()

        return report_id

    def get_report(self, username: str, year: int) -> Optional[Dict]:
        """Retrieve a contribution report"""
        query = """
        SELECT * FROM contribution_reports
        WHERE username = %s AND year = %s
        """

        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (username, year))
                result = cur.fetchone()

        if result:
            result["languages"] = json.loads(result["languages"])

        return result

    def save_telegram_user(self, telegram_id: int, github_username: str = None):
        """Save or update Telegram user"""
        query = """
        INSERT INTO telegram_users (telegram_id, github_username, last_query)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (telegram_id) DO UPDATE SET
            github_username = COALESCE(EXCLUDED.github_username, telegram_users.github_username),
            last_query = CURRENT_TIMESTAMP
        """

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (telegram_id, github_username))
            conn.commit()


class TelegramBot:
    """Telegram bot interface"""

    def __init__(
        self,
        token: str,
        github_analyzer: GitHubAnalyzer,
        db_manager: DatabaseManager,
    ):
        self.token = token
        self.github = github_analyzer
        self.db = db_manager
        self.app = None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        self.db.save_telegram_user(user_id)

        welcome_message = (
            "🚀 *GitHub Contribution Analyzer Bot*\n\n"
            "I can analyze GitHub contributions for any user!\n\n"
            "*Commands:*\n"
            "/analyze `username` - Analyze current year\n"
            "/analyze `username` `year` - Analyze specific year\n"
            "/cached `username` `year` - Get cached report\n"
            "/help - Show this help message\n\n"
            "*Example:* `/analyze torvalds 2024`"
        )

        await update.message.reply_text(welcome_message, parse_mode="Markdown")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await self.start(update, context)

    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a GitHub username!\nUsage: `/analyze username [year]`",
                parse_mode="Markdown",
            )
            return

        username = context.args[0]
        year = int(context.args[1]) if len(context.args) > 1 else datetime.now().year

        # Validate year
        if year < 2008 or year > datetime.now().year:
            await update.message.reply_text(
                f"Invalid year! Please choose between 2008 and {datetime.now().year}"
            )
            return

        # Send loading message
        loading_msg = await update.message.reply_text(
            f"🔍 Analyzing contributions for *{username}* in {year}...",
            parse_mode="Markdown",
        )

        try:
            # Fetch data from GitHub
            stats = await self.github.get_user_contributions(username, year)

            # Save to database
            self.db.save_report(stats)
            self.db.save_telegram_user(update.effective_user.id, username)

            # Format and send report
            report = self._format_report(stats)

            await loading_msg.edit_text(report, parse_mode="Markdown")

            # Add inline keyboard for actions
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📊 Language Stats", callback_data=f"lang_{username}_{year}"
                    ),
                    InlineKeyboardButton(
                        "📈 Compare Years", callback_data=f"compare_{username}"
                    ),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Select an option for more details:", reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error analyzing {username}: {e}")
            await loading_msg.edit_text(
                f"❌ Error analyzing {username}: {str(e)}\n"
                "Make sure the username is correct and try again."
            )

    async def cached(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cached command"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: `/cached username year`", parse_mode="Markdown"
            )
            return

        username = context.args[0]
        year = int(context.args[1])

        report = self.db.get_report(username, year)
        if report:
            stats = ContributionStats(**report)
            formatted = self._format_report(stats)
            await update.message.reply_text(
                f"{formatted}\n\n_📅 Cached report from {report['created_at'].strftime('%Y-%m-%d %H:%M UTC')}_",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"No cached report found for {username} in {year}.\n"
                f"Use `/analyze {username} {year}` to generate one.",
                parse_mode="Markdown",
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()

        data = query.data.split("_")
        action = data[0]

        if action == "lang":
            username = data[1]
            year = int(data[2])
            report = self.db.get_report(username, year)
            if report and report["languages"]:
                languages = report["languages"]
                sorted_langs = sorted(
                    languages.items(), key=lambda x: x[1], reverse=True
                )

                lang_text = f"*Language Statistics for {username} ({year})*\n\n"
                for lang, count in sorted_langs[:10]:
                    percentage = (count / sum(languages.values())) * 100
                    bar = "█" * int(percentage / 5)
                    lang_text += (
                        f"`{lang:<12}` {bar} {percentage:.1f}% ({count} commits)\n"
                    )

                await query.message.reply_text(lang_text, parse_mode="Markdown")

        elif action == "compare":
            username = data[1]
            current_year = datetime.now().year

            comparison_text = f"*Year-over-Year Comparison for {username}*\n\n"

            for year in range(current_year - 2, current_year + 1):
                report = self.db.get_report(username, year)
                if report:
                    comparison_text += (
                        f"*{year}:*\n"
                        f"• Commits: {report['total_commits']}\n"
                        f"• PRs: {report['total_prs']}\n"
                        f"• Issues: {report['total_issues']}\n\n"
                    )

            await query.message.reply_text(comparison_text, parse_mode="Markdown")

    def _format_report(self, stats: ContributionStats) -> str:
        """Format contribution stats for Telegram"""
        total_contributions = (
            stats.total_commits
            + stats.total_prs
            + stats.total_issues
            + stats.total_discussions
        )

        report = f"""
*GitHub Contributions Report*
👤 User: `{stats.username}`
📅 Year: {stats.year}

*📊 Contribution Summary*
• Total Contributions: *{total_contributions:,}*
• Commits: *{stats.total_commits:,}*
• Pull Requests: *{stats.total_prs:,}*
• Issues: *{stats.total_issues:,}*
• Discussions: *{stats.total_discussions:,}*
• Code Reviews: *{stats.total_reviews:,}*

*💻 Code Statistics*
• Lines Added: *{stats.lines_added:,}*
• Lines Deleted: *{stats.lines_deleted:,}*
• Net Lines: *{stats.lines_added - stats.lines_deleted:,}*

*📈 Activity Metrics*
• Repositories Contributed: *{stats.repositories_contributed}*
• Public Repositories: *{stats.public_repos}*
• Private Contributions: *{stats.private_contributions}*

*🌟 Social Stats*
• Starred Repos: *{stats.starred_repos:,}*
• Followers: *{stats.followers:,}*
• Following: *{stats.following:,}*

*🔥 Top Languages*
"""

        # Add top 5 languages
        if stats.languages:
            sorted_langs = sorted(
                stats.languages.items(), key=lambda x: x[1], reverse=True
            )[:5]
            for i, (lang, count) in enumerate(sorted_langs, 1):
                report += f"{i}. {lang}: {count} commits\n"
        else:
            report += "No language data available\n"

        return report

    def run(self):
        """Start the Telegram bot"""
        self.app = Application.builder().token(self.token).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("analyze", self.analyze))
        self.app.add_handler(CommandHandler("cached", self.cached))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        # Start polling
        logger.info("Starting Telegram bot...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Main entry point"""
    # Validate environment variables
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN not set!")
        return

    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set!")
        return

    # Initialize components
    github_analyzer = GitHubAnalyzer(GITHUB_TOKEN)
    db_manager = DatabaseManager(DATABASE_URL)
    telegram_bot = TelegramBot(
        TELEGRAM_TOKEN,
        github_analyzer,
        db_manager,
    )

    # Run the bot
    try:
        telegram_bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")


if __name__ == "__main__":
    main()
