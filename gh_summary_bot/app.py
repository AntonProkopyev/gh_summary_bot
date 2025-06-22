import asyncio
import logging
import os
from typing import Optional

import aiopg
from dotenv import load_dotenv

from .bot import GitHubBotCommands, TelegramBotApp
from .templates import TelegramReportTemplate
from .github_source import GitHubContributionSource, GraphQLClient, RequestConfig
from .storage import (
    CompositeStorage,
    DatabaseInitializer,
    PostgreSQLReportStorage,
    PostgreSQLUserStorage,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class ApplicationConfig:
    def __init__(self):
        self.github_token: str = os.environ["GITHUB_TOKEN"]
        self.telegram_token: str = os.environ["TELEGRAM_TOKEN"]
        self.database_url: str = os.environ["DATABASE_URL"]

    def validate(self) -> None:
        """Validate configuration."""
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN not set!")

        if not self.telegram_token:
            raise ValueError("TELEGRAM_TOKEN not set!")

        if not self.database_url:
            raise ValueError("DATABASE_URL not set!")


class DatabasePool:
    """Database connection pool wrapper."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool: Optional[aiopg.Pool] = None

    async def initialize(self) -> aiopg.Pool:
        """Initialize and return connection pool."""
        if not self._pool:
            self._pool = await aiopg.create_pool(self._database_url)

            # Initialize database tables
            initializer = DatabaseInitializer(self._pool)
            await initializer.initialize_tables()

        return self._pool

    async def close(self) -> None:
        """Close connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()


class Application:
    def __init__(self, config: ApplicationConfig):
        self._config = config

    async def run(self) -> None:
        try:
            # Validate configuration
            self._config.validate()
            assert self._config.database_url is not None
            assert self._config.github_token is not None
            assert self._config.telegram_token is not None

            db_pool_wrapper = DatabasePool(self._config.database_url)
            pool = await db_pool_wrapper.initialize()
            storage = CompositeStorage(
                PostgreSQLReportStorage(pool),
                PostgreSQLUserStorage(pool),
            )
            github_config = RequestConfig(
                base_url="https://api.github.com/graphql",
                token=self._config.github_token,
            )
            client = GraphQLClient(github_config)
            github_source = GitHubContributionSource(client)
            template = TelegramReportTemplate()
            bot_commands = GitHubBotCommands(github_source, storage, template)
            bot = TelegramBotApp(self._config.telegram_token, bot_commands)
            await bot.run()

        except KeyboardInterrupt:
            logger.info("Application stopped by user")
        except Exception as e:
            logger.error(f"Application error: {e}")
        finally:
            if db_pool_wrapper:
                await db_pool_wrapper.close()


async def main():
    config = ApplicationConfig()
    app = Application(config)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
