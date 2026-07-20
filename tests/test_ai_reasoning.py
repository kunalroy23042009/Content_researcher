"""Tests for Phase 8 — AI reasoning."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.ai_reasoning import (
    FALLBACK_SUMMARY,
    _build_prompt,
    _select_results_for_prompt,
    generate_insights,
)
from app.models import ChannelProfile, ContentResult, TopicInsight


NOW = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)


def _profile() -> ChannelProfile:
    return ChannelProfile(
        channel_id="UCsource1234567890123456",
        title="Budget Tech Daily",
        description="Affordable tech reviews for students.",
        subscriber_count=25_000,
        video_count=80,
        view_count=1_200_000,
        recent_video_titles=["Best $300 laptop", "Chromebook vs Windows"],
        niche="budget tech reviews",
        topics=["laptops", "chromebooks", "student tech"],
        content_style="concise, friendly how-to reviews",
        target_audience="budget-conscious students",
        ai_summary="Short-form reviews of affordable tech gear.",
    )


def _result(
    title: str,
    engagement: float,
    classification: str = "trending",
    platform: str = "youtube",
) -> ContentResult:
    return ContentResult(
        platform=platform,  # type: ignore[arg-type]
        title=title,
        url=f"https://example.com/{title}",
        engagement_score=engagement,
        published_at=NOW,
        source="Tech Channel" if platform == "youtube" else "r/laptops",
        raw_metrics={"views": int(engagement), "likes": 10},
        classification=classification,  # type: ignore[arg-type]
    )


def _valid_insight_json() -> str:
    return json.dumps(
        {
            "summary": (
                "Budget laptop content is surging on YouTube, especially comparisons "
                "under $400. Reddit threads focus on student use cases."
            ),
            "content_angles": [
                "Film a 'Best $300 laptop for college 2025' video referencing the trending "
                "'Acer Aspire review' title in your concise review style.",
                "Create a Chromebook vs Windows side-by-side aimed at students, matching "
                "your friendly how-to tone from recent titles.",
                "Post a Reddit AMA-style follow-up video answering top r/laptops questions "
                "about budget picks.",
            ],
            "content_gap": "No creator is covering refurbished laptop warranties under $250.",
        }
    )


def test_generate_insights_parses_valid_response():
    profile = _profile()
    results = [
        _result("Acer Aspire review", 12_000),
        _result("Best cheap laptop Reddit", 800, platform="reddit"),
    ]

    mock_response = MagicMock()
    mock_response.text = _valid_insight_json()
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.ai_reasoning._get_gemini_client", return_value=mock_client):
        insight = generate_insights(profile, "budget laptop", results)

    assert isinstance(insight, TopicInsight)
    assert "Budget laptop content" in insight.summary
    assert len(insight.content_angles) == 3
    assert "Acer Aspire review" in insight.content_angles[0]
    assert insight.content_gap is not None
    assert "refurbished" in insight.content_gap


def test_generate_insights_retries_once_then_succeeds():
    profile = _profile()
    results = [_result("Trending video", 5_000)]

    bad_response = MagicMock()
    bad_response.text = "not json"
    good_response = MagicMock()
    good_response.text = _valid_insight_json()

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [bad_response, good_response]

    with patch("app.ai_reasoning._get_gemini_client", return_value=mock_client):
        insight = generate_insights(profile, "budget laptop", results)

    assert mock_client.models.generate_content.call_count == 2
    assert len(insight.content_angles) == 3


def test_generate_insights_fallback_on_persistent_malformed_response():
    profile = _profile()
    results = [_result("Trending video", 5_000)]

    bad_response = MagicMock()
    bad_response.text = '{"summary": "only summary"}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = bad_response

    with patch("app.ai_reasoning._get_gemini_client", return_value=mock_client):
        insight = generate_insights(profile, "budget laptop", results)

    assert insight.summary == FALLBACK_SUMMARY
    assert insight.content_angles == []
    assert insight.content_gap is None
    assert mock_client.models.generate_content.call_count == 2


def test_generate_insights_fallback_when_client_init_fails():
    profile = _profile()
    results = [_result("Trending video", 5_000)]

    with patch("app.ai_reasoning._get_gemini_client", side_effect=RuntimeError("no key")):
        insight = generate_insights(profile, "budget laptop", results)

    assert insight.summary == FALLBACK_SUMMARY
    assert insight.content_angles == []


def test_select_results_for_prompt_prioritizes_classified_and_engagement():
    results = [
        _result("low none", 100, classification="none"),
        _result("high none", 9_000, classification="none"),
        _result("underrated gem", 2_000, classification="underrated"),
        _result("trending hit", 20_000, classification="trending"),
        _result("popular staple", 15_000, classification="popular"),
    ]

    selected = _select_results_for_prompt(results)
    titles = [r.title for r in selected]

    assert titles[0] == "trending hit"
    assert "underrated gem" in titles[:3]


def test_build_prompt_includes_profile_topic_and_result_titles():
    profile = _profile()
    results = [
        _result("Acer Aspire review", 12_000),
        _result("Reddit budget thread", 500, platform="reddit"),
    ]

    prompt = _build_prompt(profile, "budget laptop", results)

    assert "Budget Tech Daily" in prompt
    assert "budget laptop" in prompt
    assert "Acer Aspire review" in prompt
    assert "Reddit budget thread" in prompt
    assert '"content_angles"' in prompt
