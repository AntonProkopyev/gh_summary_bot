"""Telegram bot interface for GitHub contribution analysis."""

import asyncio
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from .database import DatabaseManager
from .github_analyzer import GitHubAnalyzer
from .models import ContributionStats

logger = logging.getLogger(__name__)


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
        await self.db.save_telegram_user(user_id)

        welcome_message = (
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
            # Create progress callback
            async def progress_update(message):
                await loading_msg.edit_text(
                    f"🔍 Analyzing *{username}* ({year}): {message}",
                    parse_mode="Markdown",
                )
            
            # Fetch data from GitHub
            stats = await self.github.get_user_contributions(username, year, progress_update, self.db)

            # Save to database
            await self.db.save_report(stats)
            await self.db.save_telegram_user(update.effective_user.id, username)

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

        report = await self.db.get_report(username, year)
        if report:
            # Remove fields that aren't part of ContributionStats
            stats_data = {k: v for k, v in report.items() if k not in ['id', 'created_at']}
            stats = ContributionStats(**stats_data)
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
            report = await self.db.get_report(username, year)
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
                report = await self.db.get_report(username, year)
                if report:
                    comparison_text += (
                        f"*{year}:*\n"
                        f"• Commits: {report['total_commits']}\n"
                        f"• PRs: {report['total_prs']}\n"
                        f"• Issues: {report['total_issues']}\n\n"
                    )

            await query.message.reply_text(comparison_text, parse_mode="Markdown")

    async def alltime(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alltime command for aggregated statistics"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a GitHub username!\nUsage: `/alltime username`",
                parse_mode="Markdown",
            )
            return

        username = context.args[0]

        # Send loading message
        loading_msg = await update.message.reply_text(
            f"🔍 Checking all-time statistics for *{username}*...",
            parse_mode="Markdown",
        )

        try:
            # Get existing years from database
            existing_years = await self.db.get_existing_years(username)
            current_year = datetime.now().year
            
            # Determine which years to analyze (from 2008 to current year)
            all_years = list(range(2008, current_year + 1))
            missing_years = [year for year in all_years if year not in existing_years]
            
            if missing_years:
                await loading_msg.edit_text(
                    f"🔍 Found {len(existing_years)} existing reports for *{username}*.\n"
                    f"Analyzing {len(missing_years)} missing years: {missing_years[0]}-{missing_years[-1]}...",
                    parse_mode="Markdown",
                )
                
                # Analyze missing years
                successful_analyses = 0
                for i, year in enumerate(missing_years, 1):
                    try:
                        await loading_msg.edit_text(
                            f"🔍 Analyzing *{username}* for year {year}...\n"
                            f"Progress: {i}/{len(missing_years)} years",
                            parse_mode="Markdown",
                        )
                        
                        # Fetch data from GitHub for this year
                        async def progress_update(message):
                            await loading_msg.edit_text(
                                f"🔍 Year {year} ({i}/{len(missing_years)}): {message}",
                                parse_mode="Markdown",
                            )
                        
                        stats = await self.github.get_user_contributions(username, year, progress_update, self.db)
                        
                        # Save to database
                        await self.db.save_report(stats)
                        successful_analyses += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to analyze {username} for {year}: {e}")
                        continue
                
                if successful_analyses > 0:
                    await loading_msg.edit_text(
                        f"✅ Successfully analyzed {successful_analyses} additional years for *{username}*.\n"
                        f"Generating all-time report...",
                        parse_mode="Markdown",
                    )
                    # Save telegram user association
                    await self.db.save_telegram_user(update.effective_user.id, username)
            else:
                await loading_msg.edit_text(
                    f"🔍 All years already analyzed for *{username}*. Aggregating statistics...",
                    parse_mode="Markdown",
                )

            # Get aggregated data from database
            stats = await self.db.get_all_time_stats(username)
            
            if not stats:
                await loading_msg.edit_text(
                    f"❌ No data could be retrieved for {username}.\n"
                    f"The user may not exist or have no public contributions.",
                    parse_mode="Markdown"
                )
                return

            # Format and send report
            report = self._format_alltime_report(stats)
            await loading_msg.edit_text(report, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error getting all-time stats for {username}: {e}")
            await loading_msg.edit_text(
                f"❌ Error retrieving all-time stats for {username}: {str(e)}"
            )

    def _format_alltime_report(self, stats: dict) -> str:
        """Format all-time aggregated stats for Telegram"""
        total_contributions = (
            stats["total_commits"]
            + stats["total_prs"]
            + stats["total_issues"]
            + stats["total_discussions"]
        )

        report = f"""
*🌟 All-Time GitHub Statistics*
👤 User: `{stats["username"]}`
📅 Period: {stats["first_year"]} - {stats["last_year"]} ({stats["total_years"]} years)

*📊 Total Contributions*
• All Contributions: *{total_contributions:,}*
• Commits: *{stats["total_commits"]:,}*
• Pull Requests: *{stats["total_prs"]:,}*
• Issues: *{stats["total_issues"]:,}*
• Discussions: *{stats["total_discussions"]:,}*
• Code Reviews: *{stats["total_reviews"]:,}*

*💻 Code Statistics*
• Lines Added: *{stats["lines_added"]:,}*
• Lines Deleted: *{stats["lines_deleted"]:,}*
• Net Lines: *{stats["lines_added"] - stats["lines_deleted"]:,}*

*📈 Activity Metrics*
• Repositories Contributed: *{stats["repositories_contributed"]:,}*
• Public Repositories: *{stats["public_repos"]:,}*
• Private Contributions: *{stats["private_contributions"]:,}*

*🌟 Social Stats*
• Starred Repos: *{stats["starred_repos"]:,}*
• Followers: *{stats["followers"]:,}*
• Following: *{stats["following"]:,}*

*🔥 Top Languages (All Time)*
"""

        # Add top 10 languages
        if stats["languages"]:
            sorted_langs = sorted(
                stats["languages"].items(), key=lambda x: x[1], reverse=True
            )[:10]
            for i, (lang, count) in enumerate(sorted_langs, 1):
                report += f"{i}. {lang}: {count:,} commits\n"
        else:
            report += "No language data available\n"

        report += f"\n_📅 Last updated: {stats['last_updated'].strftime('%Y-%m-%d %H:%M UTC')}_"
        
        return report

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

    async def run(self):
        """Start the Telegram bot"""
        self.app = Application.builder().token(self.token).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("analyze", self.analyze))
        self.app.add_handler(CommandHandler("alltime", self.alltime))
        self.app.add_handler(CommandHandler("cached", self.cached))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        # Initialize and start polling
        logger.info("Starting Telegram bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        # Keep the bot running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()