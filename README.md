# GitHub Contribution Analyzer Bot

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Telegram Bot](https://img.shields.io/badge/telegram-@ghsummarybot-blue.svg)](https://t.me/ghsummarybot)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![GitHub API](https://img.shields.io/badge/GitHub%20API-v4%20GraphQL-181717?logo=github)](https://docs.github.com/en/graphql)

A sophisticated Telegram bot that analyzes GitHub user contributions using the GraphQL API and provides detailed analytics through a clean chat interface.

## Features

- **Comprehensive GitHub Analysis**: Fetches detailed contribution data including commits, PRs, issues, discussions, stars, forks, and more
- **Flexible Date Ranges**: Analyze last 12 months, specific years, or custom date ranges
- **Telegram Bot Interface**: Clean and easy-to-use chat interface
- **Async Architecture**: Fully asynchronous implementation for optimal performance
- **Rate Limit Handling**: Intelligent GitHub API rate limit management
- **User Telemetry**: Tracks user interactions for analytics

## Installation

### Prerequisites

- Python 3.13+
- PostgreSQL database
- GitHub Personal Access Token
- Telegram Bot Token

### Dependencies

```bash
# Install using uv (recommended)
uv sync
```

## Configuration

Create a `.env` file in the project root:

```env
# GitHub Personal Access Token (with read permissions)
GITHUB_TOKEN=ghp_your_token_here

# Telegram Bot Token from @BotFather
TELEGRAM_TOKEN=123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# PostgreSQL connection string
DATABASE_URL=postgresql://username:password@localhost:5432/database_name
```

### Environment Variables

| Variable         | Description                                        | Required |
| ---------------- | -------------------------------------------------- | -------- |
| `GITHUB_TOKEN`   | GitHub personal access token with read permissions | Yes      |
| `TELEGRAM_TOKEN` | Telegram bot token from @BotFather                 | Yes      |
| `DATABASE_URL`   | PostgreSQL connection string                       | Yes      |

## Usage

### Running the Bot

```bash
# Using uv (recommended)
uv run python -m gh_summary_bot

# Or directly with Python
python -m gh_summary_bot
```

### Telegram Commands

- `/start` - Welcome message and help
- `/help` - Show available commands
- `/analyze username` - Analyze last 12 months (default)
- `/analyze username year` - Analyze specific year (e.g., 2024)
- `/analyze username start-date end-date` - Custom date range (YYYY-MM-DD format)

### Examples

```
/analyze torvalds            # Last 12 months
/analyze torvalds 2024       # Year 2024
/analyze torvalds 2024-01-01 2024-06-30  # Custom range
```

### Features

- **Real-time Analysis**: Fresh data from GitHub API for every request
- **Multiple Date Formats**: Flexible date range options
- **Line Statistics**: Tracks lines added/deleted with fallback calculation methods

## Development

For detailed architecture information, database schema, and implementation details, see [ARCHITECTURE.md](ARCHITECTURE.md).

### Contributing

1. Install dependencies: `uv sync`
2. Setup pre-commit hooks: `./scripts/setup-hooks.sh`
3. Ensure all tests pass
4. Follow the existing code style (enforced by ruff)
5. Add tests for new features
6. Update documentation as needed

The pre-commit hooks will automatically run `ruff check` and `ruff format --check` before each commit to ensure code quality.

## License

This project is open source. See the license file for details.

## Support

For issues and feature requests, please use the project's issue tracker.

## Try the Bot

You can try the bot directly on Telegram: https://t.me/ghsummarybot
