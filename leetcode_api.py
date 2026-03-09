"""
LeetCode API integration using the unofficial GraphQL API.
Checks if a user has solved a specific problem by its slug.
No authentication required for public submission data.
"""

import aiohttp
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict

# IST = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

# GraphQL query to fetch recent accepted submissions for a user
RECENT_SUBMISSIONS_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
}
"""

# GraphQL query to verify a LeetCode username exists
USER_EXISTS_QUERY = """
query userPublicProfile($username: String!) {
  matchedUser(username: $username) {
    username
  }
}
"""

def get_slug_from_url(url: str) -> str:
    """Extract problem slug from a LeetCode URL.
    e.g. https://leetcode.com/problems/two-sum/ -> two-sum
    """
    parts = url.rstrip("/").split("/")
    return parts[-1]


async def verify_leetcode_user(username: str) -> bool:
    """Check if a LeetCode username exists."""
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "query": USER_EXISTS_QUERY,
        "variables": {"username": username}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LEETCODE_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                matched = data.get("data", {}).get("matchedUser")
                return matched is not None
    except Exception:
        return False


async def check_problem_solved(leetcode_username: str, problem_url: str, limit: int = 20) -> bool:
    """
    Check if a user has solved a specific problem TODAY (in IST).
    Returns True only if an accepted submission exists for the problem slug
    and was submitted on today's date in IST.
    """
    slug = get_slug_from_url(problem_url)
    today_ist = datetime.now(IST).date()

    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "query": RECENT_SUBMISSIONS_QUERY,
        "variables": {"username": leetcode_username, "limit": limit}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LEETCODE_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return False
                data = await resp.json()
                submissions = (
                    data.get("data", {})
                        .get("recentAcSubmissionList", []) or []
                )
                for s in submissions:
                    if s.get("titleSlug") != slug:
                        continue
                    # Convert Unix timestamp to IST date
                    ts = int(s.get("timestamp", 0))
                    submission_date = datetime.fromtimestamp(ts, tz=IST).date()
                    if submission_date == today_ist:
                        return True
                return False
    except Exception:
        return False


async def get_recent_solves(leetcode_username: str, limit: int = 10) -> list:
    """Get a list of recently solved problem slugs."""
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "query": RECENT_SUBMISSIONS_QUERY,
        "variables": {"username": leetcode_username, "limit": limit}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                LEETCODE_GRAPHQL_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("data", {}).get("recentAcSubmissionList", []) or []
    except Exception:
        return []
