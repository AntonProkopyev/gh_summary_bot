# Architecture Documentation

This document provides detailed information about the internal architecture and implementation details of the GitHub Contribution Analyzer Bot.

## Architecture Overview

The bot is built using Elegant Objects principles with PostgreSQL for data persistence and the Telegram Bot API for user interaction. The system uses proper data structures instead of dictionaries, protocol-based interfaces, and is designed to handle GitHub's API rate limits gracefully while providing fast responses through intelligent caching.

## Core Components

### GraphQLClient (`gh_summary_bot/github_source.py:64-147`)

GraphQL client for GitHub API with automatic rate limit handling. This component:

- Manages GitHub API authentication using request configurations
- Handles automatic rate limiting with exponential backoff
- Provides context manager pattern for resource management
- Implements comprehensive error handling for API failures
- Uses `RateLimit` and `RequestConfig` models

### GitHubContributionSource (`gh_summary_bot/github_source.py:93-467`)

GitHub contribution data source with integrated line calculation. Features:

- Fetches user contribution statistics using query configurations
- Calculates line statistics automatically within contributions method
- Returns `ContributionStats`, `Commit`, and `PullRequest` objects
- Handles complex multi-query operations for commit and PR data
- Implements proper error handling with fallback for line calculation failures
- Uses `YearRange` for date management

### PostgreSQLReportStorage (`gh_summary_bot/storage.py:13-218`)

PostgreSQL operations using aiopg connection pooling. Responsibilities:

- Stores and retrieves `ContributionStats` objects
- Returns `CachedReport` and `AllTimeStats` objects
- Implements CRUD operations
- Provides transaction-safe operations using context managers
- Uses proper serialization/deserialization

### TelegramBotApp (`gh_summary_bot/bot.py:219-365`)

Telegram bot application. Includes:

- Command routing using command handlers
- Context management for bot lifecycle
- Proper separation of concerns with `GitHubBotCommands`
- Error handling

### GitHubBotCommands (`gh_summary_bot/bot.py:40-217`)

GitHub bot command implementations. Features:

- Command processing using structured data
- Progress reporting through protocol-based interfaces
- Returns formatted strings without side effects
- Delegates to storage and formatting components

## Data Models

### ContributionStats (`gh_summary_bot/models.py:8-28`)
GitHub contribution statistics for a specific year:
- Contains all yearly contribution metrics
- Used for primary data transfer

### AllTimeStats (`gh_summary_bot/models.py:32-53`)
All-time aggregated GitHub statistics:
- Aggregates data across multiple years
- Contains cumulative and snapshot metrics
- Used for all-time reporting

### CachedReport (`gh_summary_bot/models.py:57-77`)
Cached contribution report data:
- Includes database metadata (id, created_at)
- Converts to ContributionStats for processing
- Used for cache retrieval operations

### Commit (`gh_summary_bot/models.py:81-88`)
Commit information:
- Contains commit metadata and line changes
- Used for accurate line count calculations

### PullRequest (`gh_summary_bot/models.py:92-97`)
Pull request information:
- Contains PR creation date and line changes
- Used for PR analysis and caching

### LineStats (`gh_summary_bot/models.py:90-96`)
Line statistics container:
- Contains lines added/deleted counts and PR count
- Used internally for line calculation from pull requests
- Provides fallback data when line calculation fails

## Data Flow

1. **Initialization**: Application starts and establishes database connection pool
2. **User Request**: Telegram user issues a command (`/analyze`, `/cached`, or `/alltime`) through TelegramBotApp
3. **Command Processing**: GitHubBotCommands processes requests using structured parameters
4. **Data Fetching**: GitHubContributionSource queries GitHub GraphQL API through GraphQLClient
5. **Line Calculation**: Line statistics calculated automatically within contributions method using pull request data
6. **Results**: All API responses converted to structured objects (ContributionStats, Commit, PullRequest)
7. **Caching Strategy**: PostgreSQLReportStorage stores/updates reports in PostgreSQL
8. **Response Generation**: TelegramReportTemplate formats results and provides interactive buttons
9. **Follow-up Interactions**: Users can request detailed views through callback buttons

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

## Elegant Objects Compliance

This codebase follows Elegant Objects principles:

### Data Structures
- All data structures are proper objects
- No mutable state in business logic
- Configurations and request objects are structured

### No Dictionaries for Data Transfer
- Replaced all dict usage with meaningful objects
- Type-safe data transfer between components
- Proper encapsulation of data structures

### Protocol-Based Interfaces
- All major components implement protocols (interfaces)
- Dependency injection through protocol contracts
- Testable and maintainable component boundaries

### Pure Functions
- Command handlers return values without side effects
- Templates operate on data
- No global state or singletons

## Development Guidelines

When contributing to this project:

1. **Use Proper Objects**: Never use dictionaries for data transfer - create structured objects
2. **Implement Protocols**: All major components must implement protocol interfaces
3. **Handle Rate Limits**: Always consider GitHub API rate limiting
4. **Cache Intelligently**: Implement caching using structured objects for expensive operations
5. **Validate Input**: Never trust user input without validation
6. **Log Appropriately**: Provide meaningful logs for debugging
7. **Test Error Paths**: Ensure error conditions are properly handled
8. **No Implementation Inheritance**: Favor composition and protocol implementation
9. **Pure Functions**: Avoid side effects in business logic