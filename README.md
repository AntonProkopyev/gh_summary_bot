# GitHub Contribution Analyzer Bot

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Telegram Bot](https://img.shields.io/badge/telegram-@ghsummarybot-blue.svg)](https://t.me/ghsummarybot)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![GitHub API](https://img.shields.io/badge/GitHub%20API-v4%20GraphQL-181717?logo=github)](https://docs.github.com/en/graphql)

A sophisticated Telegram bot that analyzes GitHub user contributions using the GraphQL API, stores reports in PostgreSQL, and provides detailed analytics through an interactive chat interface.

## Features

- **Comprehensive GitHub Analysis**: Fetches detailed contribution data including commits, PRs, issues, discussions, stars, forks, and more
- **PostgreSQL Storage**: Persistent storage of contribution reports with caching capabilities
- **Telegram Bot Interface**: Easy-to-use chat interface with interactive buttons for detailed views
- **Async Architecture**: Fully asynchronous implementation for optimal performance
- **Rate Limit Handling**: Intelligent GitHub API rate limit management
- **Language Statistics**: Detailed breakdown of programming languages used
- **Year-over-Year Comparison**: Compare contributions across different years

## Architecture

### Core Components

- **GitHubGraphQLClient** (`gh_gql_client.py`): Async GitHub GraphQL client with automatic rate limit handling and pagination support
- **GitHubAnalyzer** (`github_analyzer.py`): High-level interface for fetching comprehensive user contribution data
- **DatabaseManager** (`database.py`): Async PostgreSQL operations using aiopg connection pooling
- **TelegramBot** (`telegram_bot.py`): Interactive bot interface with command handlers and callback management
- **ContributionStats** (`models.py`): Data class containing all GitHub contribution statistics

### Data Flow

1. Application initializes async database connection pool on startup
2. Telegram user requests analysis via `/analyze username [year]`
3. GitHubAnalyzer queries GitHub GraphQL API for comprehensive contribution data
4. DatabaseManager stores/updates the report in PostgreSQL using async operations
5. TelegramBot formats and displays the results with interactive buttons for detailed views

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

# Or install manually
pip install python-telegram-bot aiopg aiohttp python-dotenv
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
# Using uv
uv run python -m gh_summary_bot

# Or directly with Python
python -m gh_summary_bot
```

### Telegram Commands

- `/start` - Welcome message and help
- `/help` - Show available commands
- `/analyze username [year]` - Analyze contributions for a user (defaults to current year)
- `/cached username year` - Retrieve cached report

### Examples

```
/analyze torvalds 2024
/analyze octocat
/cached torvalds 2023
```

### Interactive Features

After running an analysis, use the interactive buttons to:

- **Language Stats**: View detailed programming language breakdown
- **Compare Years**: Compare contributions across multiple years

## Database Schema

### contribution_reports

Stores all GitHub contribution statistics with unique constraint on (username, year):

```sql
CREATE TABLE contribution_reports (
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
```

### telegram_users

Maps Telegram users to GitHub usernames for convenience:

```sql
CREATE TABLE telegram_users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    github_username VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_query TIMESTAMP
);
```

## Development

### Contributing

1. Ensure all tests pass
2. Follow the existing code style
3. Add tests for new features
4. Update documentation as needed

## API Rate Limits

The bot automatically handles GitHub API rate limits:

- Monitors remaining requests
- Automatically waits when limits are approached
- Provides informative logging about rate limit status

## Error Handling

- **GitHub API Errors**: Comprehensive error handling with specific messages
- **Database Errors**: Connection pooling with automatic retry
- **Telegram Errors**: Graceful handling of bot API issues
- **Rate Limiting**: Automatic backoff and retry mechanisms

## Performance

- **Async Architecture**: Non-blocking operations throughout
- **Connection Pooling**: Efficient database connection management
- **Caching**: Persistent storage reduces API calls
- **Rate Limit Optimization**: Intelligent request scheduling

## Security

- Environment variable configuration for sensitive data
- No hardcoded tokens or credentials
- Secure database connection handling
- Input validation for all user inputs

## Monitoring

The application provides comprehensive logging:

- GitHub API interactions
- Database operations
- Rate limit status
- Error conditions
- User interactions

## License

This project is open source. See the license file for details.

## Support

For issues and feature requests, please use the project's issue tracker.

## Try the Bot

You can try the bot directly on Telegram: https://t.me/ghsummarybot
