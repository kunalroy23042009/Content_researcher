"""Smoke tests for the FastAPI app."""

import pytest
from unittest.mock import patch
import httpx

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """GET /health should return 200 with status ok."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_analyze_channel_invalid_url():
    """POST /analyze-channel with invalid URL should return 400."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.main.analyze_channel") as mock_analyze:
            mock_analyze.side_effect = ValueError("Invalid YouTube URL")
            response = await client.post("/analyze-channel", json={"channel_url": "garbage"})
            assert response.status_code == 400
            assert "Invalid YouTube URL" in response.json()["detail"]


@pytest.mark.asyncio
async def test_search_topic_missing_fields():
    """POST /search-topic with missing required fields should return 422."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Missing channel_id
        response = await client.post("/search-topic", json={"topic": "test"})
        assert response.status_code == 422

        # Missing topic
        response = await client.post("/search-topic", json={"channel_id": "UC123"})
        assert response.status_code == 422

        # Missing both
        response = await client.post("/search-topic", json={})
        assert response.status_code == 422
