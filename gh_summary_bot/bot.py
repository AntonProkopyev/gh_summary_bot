import asyncio
import logging
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from telegram.ext import Application

from telegram import Update
from telegram.ext import Application
from telegram.ext import CommandHandler
from telegram.ext import ContextTypes

from .models import DateRange
from .protocols import GitHubSource
from .storage import PostgreSQLUserStorage
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
        user_storage: PostgreSQLUserStorage,
        template: TelegramReportTemplate,
    ) -> None:
        self._github = github_source
        self._user_storage = user_storage
        self._template = template

    async def start_command(self, user_id: int) -> str:
        await self._user_storage.store_user(user_id)

        return (
            "🚀 *GitHub Contribution Analyzer Bot*\n\n"
            "I can analyze GitHub contributions for any user!\n\n"
            "*Commands:*\n"
            "/analyze `username` - Analyze last 12 months (default)\n"
            "/analyze `username` `year` - Analyze specific year\n"
            "/analyze `username` `start-date` `end-date` - Custom date range\n"
            "/help - Show this help message\n\n"
            "*Examples:*\n"
            "• `/analyze torvalds` - Last 12 months\n"
            "• `/analyze torvalds 2024` - Year 2024\n"
            "• `/analyze torvalds 2024-01-01 2024-06-30` - Custom range"
        )

    def _validate_year_range(self, year: int) -> None:
        """Validate year is within acceptable range."""
        current_year = datetime.now(UTC).year
        if year < 2008 or year > current_year:
            raise ValueError(f"Year must be between 2008 and {current_year}")

    def parse_date_arguments(self, args: list[str]) -> DateRange:
        """Parse date arguments into a DateRange."""
        if len(args) == 0:
            # Default to last 12 months
            return DateRange.last_12_months()
        if len(args) == 1:
            try:
                # Try to parse as year
                year = int(args[0])
                self._validate_year_range(year)
                return DateRange.calendar_year(year)
            except ValueError as e:
                raise ValueError("Invalid year format. Use a 4-digit year (e.g., 2024)") from e
        elif len(args) == 2:
            try:
                # Parse as start-date end-date
                return DateRange.from_strings(args[0], args[1])
            except ValueError as e:
                raise ValueError(f"Invalid date format. Use YYYY-MM-DD format: {e}") from e
        else:
            raise ValueError("Too many arguments. Use: username [year] or username start-date end-date")

    async def analyze_command(
        self, username: str, date_range: DateRange, user_id: int, progress: TelegramProgressReporter
    ) -> str:
        try:
            github_with_progress = self._github.with_progress_reporter(progress)
            stats = await github_with_progress.contributions(username, date_range)

            await self._user_storage.store_user(user_id, username)

            return self._template.yearly(stats)

        except Exception as e:
            logger.exception(f"Error analyzing {username}")
            return f"❌ Error analyzing {username}: {e!s}\nMake sure the username is correct and try again."


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
                "Please provide a GitHub username!\nUsage: `/analyze username [year|start-date end-date]`",
                parse_mode="Markdown",
            )
            return

        username = context.args[0]
        user_id = update.effective_user.id

        try:
            date_range = self._commands.parse_date_arguments(context.args[1:])
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}", parse_mode="Markdown")
            return

        loading_msg = await update.message.reply_text(
            f"🔍 Analyzing contributions for *{username}* ({date_range.description()})...",
            parse_mode="Markdown",
        )

        progress = TelegramProgressReporter(loading_msg, username)

        report = await self._commands.analyze_command(username, date_range, user_id, progress)
        await loading_msg.edit_text(report, parse_mode="Markdown")

    async def run(self) -> None:
        self._app = Application.builder().token(self._token).build()
        assert self._app is not None  # Help mypy understand _app is not None

        self._app.add_handler(CommandHandler("start", self.start))
        self._app.add_handler(CommandHandler("help", self.help))
        self._app.add_handler(CommandHandler("analyze", self.analyze))

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
