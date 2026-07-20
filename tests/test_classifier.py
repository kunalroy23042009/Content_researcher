"""
Tests for the content classifier.
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.classifier import classify_results
from app.models import ContentResult


def make_result(platform="youtube", views=1000, published_hours_ago=24, title="Test Video"):
    published_at = datetime.now(timezone.utc) - timedelta(hours=published_hours_ago)
    return ContentResult(
        platform=platform,
        title=title,
        url="https://example.com/video",
        engagement_score=float(views),
        published_at=published_at,
        classification="",
        raw_metrics={"views": views},
    )


def test_classify_empty():
    assert classify_results([]) == []


def test_classify_single_result():
    result = make_result(views=5000, published_hours_ago=12)
    classified = classify_results([result])
    assert len(classified) == 1
    assert classified[0].classification in {"trending", "popular", "underrated", ""}


def test_classify_trending():
    # Fresh, high engagement content should be trending
    results = [
        make_result(views=100_000, published_hours_ago=6, title="Viral Video"),
        make_result(views=100, published_hours_ago=200, title="Old Video"),
    ]
    classified = classify_results(results)
    titles = {r.title: r.classification for r in classified}
    assert titles["Viral Video"] in {"trending", "popular"}


def test_classify_popular():
    results = [make_result(views=1_000_000, published_hours_ago=500) for _ in range(5)]
    classified = classify_results(results)
    for r in classified:
        assert r.classification in {"popular", "trending", "underrated", ""}


def test_classify_mixed_platforms():
    results = [
        make_result(platform="youtube", views=5000, published_hours_ago=48),
        make_result(platform="reddit", views=200, published_hours_ago=12),
    ]
    classified = classify_results(results)
    assert len(classified) == 2
    for r in classified:
        assert r.classification in {"trending", "popular", "underrated", ""}


def test_all_results_have_classification():
    results = [make_result(views=i*100, published_hours_ago=i*10) for i in range(1, 10)]
    classified = classify_results(results)
    for r in classified:
        assert r.classification is not None
