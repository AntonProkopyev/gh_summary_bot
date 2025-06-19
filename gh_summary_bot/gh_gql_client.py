import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RateLimitInfo:
    """Rate limit information from GitHub API response headers"""

    limit: int
    remaining: int
    reset_at: datetime
    used: int
    node_count: int

    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> "RateLimitInfo":
        """Create RateLimitInfo from response headers"""
        return cls(
            limit=int(headers.get("x-ratelimit-limit", 0)),
            remaining=int(headers.get("x-ratelimit-remaining", 0)),
            reset_at=datetime.fromtimestamp(
                int(headers.get("x-ratelimit-reset", 0)), tz=timezone.utc
            ),
            used=int(headers.get("x-ratelimit-used", 0)),
            node_count=int(headers.get("x-ratelimit-resource", 0)),
        )

    @property
    def seconds_until_reset(self) -> float:
        """Calculate seconds until rate limit resets"""
        return max(0, (self.reset_at - datetime.now(timezone.utc)).total_seconds())


class GitHubGraphQLClient:
    """
    Async GitHub GraphQL client with automatic rate limit handling
    """

    def __init__(self, token: str, base_url: str = "https://api.github.com/graphql"):
        self.token = token
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limit_info: Optional[RateLimitInfo] = None

        # Rate limiting configuration
        self.min_remaining_threshold = 100  # Pause when remaining < this
        self.safety_buffer = 10  # Extra seconds to wait after reset

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_session()

    async def start_session(self):
        """Initialize aiohttp session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github.v4+json",
            "User-Agent": "GitHub-GraphQL-Python-Client/1.0",
        }

    async def _check_rate_limit(self):
        """Check if we need to wait for rate limit reset"""
        if not self.rate_limit_info:
            return

        if self.rate_limit_info.remaining < self.min_remaining_threshold:
            wait_time = self.rate_limit_info.seconds_until_reset + self.safety_buffer
            if wait_time > 0:
                logger.warning(
                    f"Rate limit nearly exhausted. "
                    f"Remaining: {self.rate_limit_info.remaining}/{self.rate_limit_info.limit}. "
                    f"Waiting {wait_time:.1f} seconds until reset."
                )
                await asyncio.sleep(wait_time)

    def _update_rate_limit_info(self, headers: Dict[str, str]):
        """Update rate limit information from response headers"""
        try:
            self.rate_limit_info = RateLimitInfo.from_headers(headers)
            logger.debug(
                f"Rate limit updated: {self.rate_limit_info.remaining}/"
                f"{self.rate_limit_info.limit} remaining"
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse rate limit headers: {e}")

    async def _make_request(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make GraphQL request with rate limit handling"""
        if not self.session:
            await self.start_session()

        # Check rate limit before making request
        await self._check_rate_limit()

        payload = {"query": query, "variables": variables or {}}

        headers = self._get_headers()

        try:
            async with self.session.post(
                self.base_url, json=payload, headers=headers
            ) as response:
                # Update rate limit info from response headers
                self._update_rate_limit_info(dict(response.headers))

                # Handle HTTP errors
                if response.status == 401:
                    raise GitHubGraphQLError("Authentication failed. Check your token.")
                elif response.status == 403:
                    raise GitHubGraphQLError(
                        "Forbidden. You may have exceeded rate limits."
                    )
                elif response.status >= 400:
                    error_text = await response.text()
                    raise GitHubGraphQLError(f"HTTP {response.status}: {error_text}")

                # Parse JSON response
                try:
                    data = await response.json()
                except json.JSONDecodeError as e:
                    raise GitHubGraphQLError(f"Failed to parse JSON response: {e}")

                # Check for GraphQL errors
                if "errors" in data:
                    errors = data["errors"]
                    error_messages = [
                        error.get("message", "Unknown error") for error in errors
                    ]
                    raise GitHubGraphQLError(
                        f"GraphQL errors: {'; '.join(error_messages)}"
                    )

                return data

        except aiohttp.ClientError as e:
            raise GitHubGraphQLError(f"Request failed: {e}")

    async def query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a GraphQL query

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Dict containing the response data

        Raises:
            GitHubGraphQLError: If the request fails or returns errors
        """
        response = await self._make_request(query, variables)
        return response.get("data", {})

    async def paginated_query(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
        max_pages: Optional[int] = None,
    ):
        """
        Execute a paginated GraphQL query using cursors

        Args:
            query: GraphQL query string (should include cursor-based pagination)
            variables: Optional variables for the query
            page_size: Number of items per page (default: 100)
            max_pages: Maximum number of pages to fetch (None for all)

        Yields:
            Dict: Each page of results
        """
        variables = variables or {}
        variables["first"] = page_size

        page_count = 0
        has_next_page = True
        cursor = None

        while has_next_page and (max_pages is None or page_count < max_pages):
            if cursor:
                variables["after"] = cursor

            data = await self.query(query, variables)
            yield data

            # Try to extract pagination info (this is a common pattern)
            # You may need to adjust this based on your specific query structure
            page_info = None
            for key, value in data.items():
                if isinstance(value, dict) and "pageInfo" in value:
                    page_info = value["pageInfo"]
                    break

            if page_info:
                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")
            else:
                # If no pageInfo found, assume no more pages
                has_next_page = False

            page_count += 1

            # Log progress
            logger.info(f"Fetched page {page_count}, has_next_page: {has_next_page}")

    def get_rate_limit_status(self) -> Optional[RateLimitInfo]:
        """Get current rate limit status"""
        return self.rate_limit_info


class GitHubGraphQLError(Exception):
    """Custom exception for GitHub GraphQL API errors"""

    pass
