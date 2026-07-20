"""Tests for Phase 6 — topic search."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models import ContentResult
from app.topic_search import search_reddit, search_topic, search_youtube


def _youtube_search_item(video_id: str, channel_title: str = "Tech Channel") -> dict:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": f"Video {video_id}",
            "channelTitle": channel_title,
            "publishedAt": "2025-06-01T12:00:00Z",
        },
    }


def _youtube_video_item(video_id: str, views: int = 1000, likes: int = 50) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": f"Video {video_id}",
            "channelTitle": "Tech Channel",
            "publishedAt": "2025-06-01T12:00:00Z",
        },
        "statistics": {"viewCount": str(views), "likeCount": str(likes)},
    }


def _reddit_submission(
    submission_id: str,
    title: str = "Reddit post",
    subreddit: str = "python",
    score: int = 120,
    comments: int = 15,
) -> MagicMock:
    submission = MagicMock()
    submission.id = submission_id
    submission.title = title
    submission.permalink = f"/r/{subreddit}/comments/{submission_id}/slug/"
    submission.score = score
    submission.num_comments = comments
    submission.created_utc = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    submission.subreddit.display_name = subreddit
    return submission


def test_search_youtube_deduplicates_and_populates_fields():
    search_responses = [
        {"items": [_youtube_search_item("vid1"), _youtube_search_item("vid2")]},
        {"items": [_youtube_search_item("vid2"), _youtube_search_item("vid3")]},
    ]
    video_response = {
        "items": [
            _youtube_video_item("vid1", views=5000, likes=200),
            _youtube_video_item("vid2", views=3000, likes=100),
            _youtube_video_item("vid3", views=800, likes=20),
        ]
    }

    mock_youtube = MagicMock()
    mock_youtube.search.return_value.list.return_value.execute.side_effect = search_responses
    mock_youtube.videos.return_value.list.return_value.execute.return_value = video_response

    with patch("app.topic_search._build_youtube_client", return_value=mock_youtube):
        results = search_youtube("budget laptop", ["UCcompetitor111111111111111"])

    assert len(results) == 3
    assert all(isinstance(r, ContentResult) for r in results)
    assert all(r.platform == "youtube" for r in results)

    by_id = {r.url.split("v=")[1]: r for r in results}
    assert by_id["vid1"].engagement_score == 5000.0
    assert by_id["vid1"].raw_metrics == {"views": 5000, "likes": 200}
    assert by_id["vid1"].source == "Tech Channel"
    assert by_id["vid1"].published_at == datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_search_youtube_returns_empty_when_no_results():
    mock_youtube = MagicMock()
    mock_youtube.search.return_value.list.return_value.execute.return_value = {"items": []}

    with patch("app.topic_search._build_youtube_client", return_value=mock_youtube):
        results = search_youtube("obscure topic", [])

    assert results == []


def test_search_reddit_searches_subreddits_with_top_and_hot():
    top_submission = _reddit_submission("post1", title="Top post", score=500)
    hot_submission = _reddit_submission("post2", title="Hot post", score=250)

    mock_subreddit = MagicMock()
    mock_subreddit.search.side_effect = [
        iter([top_submission]),
        iter([hot_submission]),
    ]

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value = mock_subreddit

    with patch("app.topic_search._build_reddit_client", return_value=mock_reddit):
        results = search_reddit("django tutorial", ["python"])

    assert len(results) == 2
    assert all(r.platform == "reddit" for r in results)
    assert results[0].engagement_score == 500.0
    assert results[0].raw_metrics["upvotes"] == 500
    assert results[0].raw_metrics["comments"] == 15
    assert results[0].source == "r/python"
    assert results[0].url.startswith("https://www.reddit.com/r/python/comments/")


def test_search_reddit_site_wide_when_no_subreddits():
    submission = _reddit_submission("post3", subreddit="all")

    mock_subreddit = MagicMock()
    mock_subreddit.search.side_effect = [iter([submission]), iter([])]

    mock_reddit = MagicMock()
    mock_reddit.subreddit.return_value = mock_subreddit

    with patch("app.topic_search._build_reddit_client", return_value=mock_reddit):
        results = search_reddit("ai news", None)

    mock_reddit.subreddit.assert_called_with("all")
    assert len(results) == 1


def test_search_reddit_returns_empty_when_client_init_fails():
    with patch("app.topic_search._build_reddit_client", side_effect=RuntimeError("no creds")):
        results = search_reddit("anything", None)

    assert results == []


def test_search_topic_merges_youtube_and_reddit():
    youtube_result = ContentResult(
        platform="youtube",
        title="YT Video",
        url="https://www.youtube.com/watch?v=abc",
        engagement_score=1000.0,
        published_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        source="YT Channel",
        raw_metrics={"views": 1000, "likes": 10},
    )
    reddit_result = ContentResult(
        platform="reddit",
        title="Reddit Post",
        url="https://www.reddit.com/r/test/comments/1/",
        engagement_score=50.0,
        published_at=datetime(2025, 6, 2, tzinfo=timezone.utc),
        source="r/test",
        raw_metrics={"upvotes": 50, "comments": 5},
    )

    with (
        patch("app.topic_search.search_youtube", return_value=[youtube_result]),
        patch("app.topic_search.search_reddit", return_value=[reddit_result]),
    ):
        results = search_topic("productivity", ["UC123"], ["productivity"])

    assert len(results) == 2
    platforms = {r.platform for r in results}
    assert platforms == {"youtube", "reddit"}


def test_search_topic_returns_partial_results_when_one_platform_fails():
    youtube_result = ContentResult(
        platform="youtube",
        title="Only YouTube",
        url="https://www.youtube.com/watch?v=xyz",
        engagement_score=500.0,
        published_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        source="Channel",
        raw_metrics={"views": 500, "likes": 5},
    )

    with (
        patch("app.topic_search.search_youtube", return_value=[youtube_result]),
        patch("app.topic_search.search_reddit", side_effect=RuntimeError("reddit down")),
    ):
        results = search_topic("topic", [], None)

    assert len(results) == 1
    assert results[0].platform == "youtube"
