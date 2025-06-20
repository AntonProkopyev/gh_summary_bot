import asyncio
import logging
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from telegram.ext import Application

from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Message
from telegram import Update
from telegram.ext import Application
from telegram.ext import CallbackQueryHandler
from telegram.ext import CommandHandler
from telegram.ext import ContextTypes

from .models import AllTimeStats
from .models import ContributionStats
from .protocols import GitHubSource
from .storage import CompositeStorage
from .templates import TelegramReportTemplate

logger = logging.getLogger(__name__)


class TelegramProgressReporter:
    """Progress reporter for Telegram messages."""

    def __init__(self, message: Any, username: str, year: int | None = None) -> None:
        self._message = message
        self._username = username
        self._year = year

    def for_year(self, year: int) -> "TelegramProgressReporter":
        """Create a new progress reporter for a specific year."""
        return TelegramProgressReporter(self._message, self._username, year)

    async def report(self, detail: str) -> None:
        if self._year:
            status = f"🔍 Analyzing *{self._username}* ({self._year}): {detail}"
        else:
            status = f"🔍 Analyzing *{self._username}*: {detail}"

        try:
            await self._message.edit_text(status, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Failed to update progress message: {e}")


class GitHubBotCommands:
    def __init__(
        self,
        github_source: GitHubSource,
        storage: CompositeStorage,
        template: TelegramReportTemplate,
    ) -> None:
        self._github = github_source
        self._storage = storage
        self._template = template

    async def start_command(self, user_id: int) -> str:
        await self._storage.users.store_user(user_id)

        return (
            "🚀 *GitHub Contribution Analyzer Bot*\n\n"
            "I can analyze GitHub contributions for any user!\n\n"
            "*Commands:*\n"
            "/analyze `username` - Analyze current year\n"
            "/analyze `username` `year` - Analyze specific year\n"
            "/alltime `username` - Get all-time aggregated stats\n"
            "/cached `username` `year` - Get cached report\n"
            "/help - Show this help message\n\n"
            "*Example:* `/analyze torvalds 2024`"
        )

    async def analyze_command(self, username: str, year: int, user_id: int, progress: TelegramProgressReporter) -> str:
        if year < 2008 or year > datetime.now(UTC).year:
            current_year = datetime.now(UTC).year
            return f"Invalid year! Please choose between 2008 and {current_year}"

        try:
            github_with_progress = self._github.with_progress_reporter(progress)
            stats = await github_with_progress.contributions(username, year)

            await self._storage.reports.store(stats)
            await self._storage.users.store_user(user_id, username)

            return self._template.yearly(stats)

        except Exception as e:
            logger.exception(f"Error analyzing {username}")
            return f"❌ Error analyzing {username}: {e!s}\nMake sure the username is correct and try again."

    async def cached_command(self, username: str, year: int) -> str:
        report = await self._storage.reports.retrieve(username, year)
        if report:
            stats = ContributionStats(
                username=report.username,
                year=report.year,
                total_commits=report.total_commits,
                total_prs=report.total_prs,
                total_issues=report.total_issues,
                total_discussions=report.total_discussions,
                total_reviews=report.total_reviews,
                repositories_contributed=report.repositories_contributed,
                languages=report.languages,
                starred_repos=report.starred_repos,
                followers=report.followers,
                following=report.following,
                public_repos=report.public_repos,
                private_contributions=report.private_contributions,
                lines_added=report.lines_added,
                lines_deleted=report.lines_deleted,
                created_at=report.created_at,
            )
            formatted = self._template.yearly(stats)
            cached_time = report.created_at.strftime("%Y-%m-%d %H:%M UTC")
            return f"{formatted}\n\n_📅 Cached report from {cached_time}_"
        return f"No cached report found for {username} in {year}.\nUse `/analyze {username} {year}` to generate one."

    async def alltime_command(self, username: str, user_id: int, progress: TelegramProgressReporter) -> str:
        try:
            existing_years = await self._storage.reports.years(username)
            current_year = datetime.now(UTC).year

            all_years = list(range(2008, current_year + 1))
            missing_years = [year for year in all_years if year not in existing_years]

            if missing_years:
                year_range = f"{missing_years[0]}-{missing_years[-1]}"
                await progress.report(
                    f"Found {len(existing_years)} existing reports. "
                    f"Analyzing {len(missing_years)} missing years: {year_range}..."
                )

                successful_analyses = 0
                for i, year in enumerate(missing_years, 1):
                    try:
                        year_progress = progress.for_year(year)
                        await year_progress.report(f"Year {year} ({i}/{len(missing_years)})")

                        github_with_progress = self._github.with_progress_reporter(year_progress)
                        stats = await github_with_progress.contributions(username, year)
                        await self._storage.reports.store(stats)
                        successful_analyses += 1

                    except Exception as e:
                        logger.warning(f"Failed to analyze {username} for {year}: {e}")
                        continue

                if successful_analyses > 0:
                    message = (
                        f"Successfully analyzed {successful_analyses} additional years. Generating all-time report..."
                    )
                    await progress.report(message)
                    await self._storage.users.store_user(user_id, username)
            else:
                await progress.report("All years already analyzed. Aggregating statistics...")

            alltime_stats: AllTimeStats | None = await self._storage.reports.aggregated(username)

            if not alltime_stats:
                return (
                    f"❌ No data could be retrieved for {username}.\n"
                    f"The user may not exist or have no public contributions."
                )

            return self._template.alltime(alltime_stats)

        except Exception as e:
            logger.exception(f"Error getting all-time stats for {username}")
            return f"❌ Error retrieving all-time stats for {username}: {e!s}"

    async def language_stats(self, username: str, year: int) -> str:
        report = await self._storage.reports.retrieve(username, year)
        if report and report.languages:
            return self._template.languages(username, year, report.languages)
        return f"No language data available for {username} ({year})"

    async def year_comparison(self, username: str) -> str:
        current_year = datetime.now(UTC).year
        comparison_text = f"*Year-over-Year Comparison for {username}*\n\n"

        for year in range(current_year - 2, current_year + 1):
            report = await self._storage.reports.retrieve(username, year)
            if report:
                comparison_text += (
                    f"*{year}:*\n"
                    f"• Commits: {report.total_commits}\n"
                    f"• PRs: {report.total_prs}\n"
                    f"• Issues: {report.total_issues}\n\n"
                )

        return comparison_text


class TelegramBotApp:
    def __init__(self, token: str, bot_commands: GitHubBotCommands) -> None:
        self._token = token
        self._commands = bot_commands
        self._app: Application | None = None

    async def start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        user_id = update.effective_user.id
        welcome_message = await self._commands.start_command(user_id)
        await update.message.reply_text(welcome_message, parse_mode="Markdown")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.start(update, context)

    async def analyze(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not context.args:
            await update.message.reply_text(
                "Please provide a GitHub username!\nUsage: `/analyze username [year]`",
                parse_mode="Markdown",
            )
            return

        username = context.args[0]
        year = int(context.args[1]) if len(context.args) > 1 else datetime.now(UTC).year
        user_id = update.effective_user.id

        loading_msg = await update.message.reply_text(
            f"🔍 Analyzing contributions for *{username}* in {year}...",
            parse_mode="Markdown",
        )

        progress = TelegramProgressReporter(loading_msg, username, year)

        report = await self._commands.analyze_command(username, year, user_id, progress)
        await loading_msg.edit_text(report, parse_mode="Markdown")

        keyboard = [
            [
                InlineKeyboardButton("📊 Language Stats", callback_data=f"lang_{username}_{year}"),
                InlineKeyboardButton("📈 Compare Years", callback_data=f"compare_{username}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Select an option for more details:", reply_markup=reply_markup)

    async def cached(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: `/cached username year`", parse_mode="Markdown")
            return

        username = context.args[0]
        year = int(context.args[1])

        report = await self._commands.cached_command(username, year)
        await update.message.reply_text(report, parse_mode="Markdown")

    async def alltime(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_user or not update.message:
            return
        if not context.args:
            await update.message.reply_text(
                "Please provide a GitHub username!\nUsage: `/alltime username`",
                parse_mode="Markdown",
            )
            return

        username = context.args[0]
        user_id = update.effective_user.id

        loading_msg = await update.message.reply_text(
            f"🔍 Checking all-time statistics for *{username}*...",
            parse_mode="Markdown",
        )

        progress = TelegramProgressReporter(loading_msg, username)

        report = await self._commands.alltime_command(username, user_id, progress)
        await loading_msg.edit_text(report, parse_mode="Markdown")

    async def button_callback(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not query.message:
            return
        await query.answer()

        data = query.data.split("_")
        action = data[0]

        if action == "lang":
            username = data[1]
            year = int(data[2])
            lang_text = await self._commands.language_stats(username, year)
            if isinstance(query.message, Message):
                await query.message.reply_text(lang_text, parse_mode="Markdown")

        elif action == "compare":
            username = data[1]
            comparison_text = await self._commands.year_comparison(username)
            if isinstance(query.message, Message):
                await query.message.reply_text(comparison_text, parse_mode="Markdown")

    async def run(self) -> None:
        self._app = Application.builder().token(self._token).build()
        assert self._app is not None  # Help mypy understand _app is not None

        self._app.add_handler(CommandHandler("start", self.start))
        self._app.add_handler(CommandHandler("help", self.help))
        self._app.add_handler(CommandHandler("analyze", self.analyze))
        self._app.add_handler(CommandHandler("alltime", self.alltime))
        self._app.add_handler(CommandHandler("cached", self.cached))
        self._app.add_handler(CallbackQueryHandler(self.button_callback))

        logger.info("Starting Telegram bot...")
        await self._app.initialize()
        await self._app.start()
        if self._app.updater:
            await self._app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            if self._app:
                if self._app.updater:
                    await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
