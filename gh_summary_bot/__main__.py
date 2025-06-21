#!/usr/bin/env python3
"""GitHub Contribution Analyzer Bot - Main application module."""

import asyncio
import logging
import os

from dotenv import load_dotenv

from .database import DatabaseManager
from .github_analyzer import GitHubAnalyzer
from .telegram_bot import TelegramBot

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


async def main():
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
    await db_manager.initialize()

    telegram_bot = TelegramBot(
        TELEGRAM_TOKEN,
        github_analyzer,
        db_manager,
    )

    # Run the bot
    try:
        await telegram_bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
