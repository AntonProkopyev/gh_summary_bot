# Architecture Documentation

This document provides detailed information about the internal architecture and implementation details of the GitHub Contribution Analyzer Bot.

## Architecture Overview

The bot is built using a fully asynchronous architecture with PostgreSQL for data persistence and the Telegram Bot API for user interaction. The system is designed to handle GitHub's API rate limits gracefully while providing fast responses through intelligent caching.

## Core Components

### GitHubGraphQLClient (`gh_summary_bot/gh_gql_client.py`)

Async GitHub GraphQL client with automatic rate limit handling and pagination support. This component:

- Manages GitHub API authentication
- Handles automatic rate limiting with exponential backoff
- Provides paginated query support for large datasets
- Implements comprehensive error handling for API failures

### GitHubAnalyzer (`gh_summary_bot/github_analyzer.py`)

High-level interface for fetching comprehensive user contribution data. Features:

- Orchestrates complex multi-query operations
- Aggregates data from multiple GitHub API endpoints
- Handles user profile, repository, and contribution queries
- Manages the relationship between cached and fresh data

### DatabaseManager (`gh_summary_bot/database.py`)

Async PostgreSQL operations using aiopg connection pooling. Responsibilities:

- Manages database connection lifecycle
- Implements CRUD operations for all data models
- Handles database schema migrations
- Provides transaction management for complex operations

### TelegramBot (`gh_summary_bot/telegram_bot.py`)

Interactive bot interface with command handlers and callback management. Includes:

- Command routing and parameter parsing
- Interactive button handling for detailed views
- User session management
- Error handling and user feedback

### ContributionStats (`gh_summary_bot/models.py`)

Data class containing all GitHub contribution statistics. This model:

- Defines the structure for contribution data
- Handles serialization/deserialization
- Provides validation for data integrity
- Supports multiple output formats

## Data Flow

1. **Initialization**: Application starts and establishes async database connection pool
2. **User Request**: Telegram user issues a command (`/analyze`, `/cached`, or `/alltime`)
3. **Data Fetching**: GitHubAnalyzer queries GitHub GraphQL API through GitHubGraphQLClient
4. **Caching Strategy**: DatabaseManager stores/updates reports in PostgreSQL with intelligent caching
5. **Response Generation**: TelegramBot formats results and provides interactive buttons
6. **Follow-up Interactions**: Users can request detailed views through callback buttons

## Database Schema

### contribution_reports

Stores yearly GitHub contribution statistics with unique constraint on (username, year):

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

Maps Telegram users to GitHub usernames for convenience and user experience optimization:

```sql
CREATE TABLE telegram_users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    github_username VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_query TIMESTAMP
);
```

### user_pull_requests

Caches pull request data for performance optimization. This table stores individual PR details separately from yearly reports, allowing for faster retrieval when analyzing users with many contributions. The caching system automatically fetches and stores PR data with additions/deletions counts to reduce GitHub API calls:

```sql
CREATE TABLE user_pull_requests (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    pr_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(username, pr_id)
);
```

## Performance Optimizations

### Caching Strategy

- **Report Caching**: Yearly reports are cached to avoid repeated API calls
- **PR Caching**: Individual pull request data is cached separately for performance
- **Smart Invalidation**: Cache is updated when new data is detected

### Rate Limit Management

- **Proactive Monitoring**: Tracks remaining API requests
- **Automatic Backoff**: Implements exponential backoff when limits approached
- **Request Batching**: Combines multiple queries where possible

### Database Optimizations

- **Connection Pooling**: Efficient database connection management
- **Unique Constraints**: Prevents duplicate data storage
- **Indexed Queries**: Optimized for common query patterns

## Error Handling

### GitHub API Errors
- Comprehensive error handling with specific user-friendly messages
- Automatic retry logic for transient failures
- Graceful degradation when API limits exceeded

### Database Errors
- Connection pooling with automatic retry mechanisms
- Transaction rollback on failure
- Data consistency validation

### Telegram Bot Errors
- Graceful handling of bot API issues
- User notification for service disruptions
- Fallback responses for unexpected errors

## Security Considerations

- **Environment Variables**: All sensitive data stored in environment variables
- **No Hardcoded Secrets**: Tokens and credentials never stored in code
- **Input Validation**: All user inputs validated and sanitized
- **Database Security**: Parameterized queries prevent SQL injection

## Monitoring and Logging

The application provides comprehensive logging for:

- GitHub API interactions and rate limit status
- Database operations and connection health
- User interactions and command usage
- Error conditions and recovery actions
- Performance metrics and query timing

## Development Guidelines

When contributing to this project:

1. **Maintain Async Patterns**: All I/O operations must be asynchronous
2. **Handle Rate Limits**: Always consider GitHub API rate limiting
3. **Cache Intelligently**: Implement caching for expensive operations
4. **Validate Input**: Never trust user input without validation
5. **Log Appropriately**: Provide meaningful logs for debugging
6. **Test Error Paths**: Ensure error conditions are properly handled