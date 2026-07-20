import logging
from datetime import datetime, timezone
import praw
from app.config import settings

logger = logging.getLogger(__name__)


class RedditClient:
    """Client for interacting with Reddit API via praw."""

    def __init__(self) -> None:
        try:
            # Wrap initialization in try-except in case of empty credentials or configuration issues
            if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
                logger.warning(
                    "Reddit client ID or client secret is not configured. "
                    "Reddit integration will operate in limited mode or fail."
                )
            self.reddit = praw.Reddit(
                client_id=settings.REDDIT_CLIENT_ID,
                client_secret=settings.REDDIT_CLIENT_SECRET,
                user_agent=settings.REDDIT_USER_AGENT,
            )
        except Exception as e:
            logger.warning("Failed to initialize praw.Reddit client: %s", e)
            self.reddit = None

    def _guess_subreddits(self, query: str) -> list[str]:
        """Map common keywords to subreddit names."""
        query_lower = query.lower()
        mappings = {
            "bmw": ["BMW", "cars", "automotive"],
            "gaming": ["gaming", "BGMI", "Minecraft"],
            "tech": ["gadgets", "technology", "laptops"],
            "car": ["cars", "automotive", "cartalk"],
            "automobile": ["cars", "automotive"],
            "automotive": ["cars", "automotive"],
            "game": ["gaming", "games"],
            "laptop": ["laptops", "suggestalaptop"],
            "gadget": ["gadgets", "technology"],
            "technology": ["technology", "tech"],
        }
        for kw, subs in mappings.items():
            if kw in query_lower:
                return subs
        return ["all"]

    def search_subreddit(
        self, query: str, subreddits: list[str] | str | None = None, limit: int = 25
    ) -> list[dict]:
        """Search a subreddit or multiple subreddits for a query."""
        if not self.reddit:
            logger.warning("Reddit client is not initialized, skipping search.")
            return []

        if not subreddits:
            subreddits = self._guess_subreddits(query)

        if isinstance(subreddits, list):
            sub_name = "+".join(subreddits)
        else:
            sub_name = subreddits

        results = []
        try:
            # sub.search is a praw call, wrap in try/except, log warning, don't crash
            sub = self.reddit.subreddit(sub_name)
            for submission in sub.search(query, limit=limit):
                # Ensure datetime is timezone-aware in UTC
                created_dt = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
                results.append(
                    {
                        "title": submission.title,
                        "url": submission.url,
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "subreddit": submission.subreddit.display_name,
                        "created_utc": created_dt,
                    }
                )
        except Exception as e:
            logger.warning(
                "Error during Reddit search for query '%s' in subreddits '%s': %s",
                query,
                sub_name,
                e,
            )

        return results
