"""Validation script for Phase 10 API Layer."""

import logging
import sys
import httpx
import asyncio
from asgiref.typing import ASGIApplication
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(".")

from app.main import app
from app.models import ChannelProfile, CompetitorChannel, ContentResult, TopicInsight

async def run_tests():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        print("Testing /health...")
        response = await ac.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        print("✓ /health passed")

        print("Testing /analyze-channel with invalid input...")
        with patch("app.main.analyze_channel") as mock_analyze:
            mock_analyze.side_effect = ValueError("Invalid YouTube URL")
            response = await ac.post("/analyze-channel", json={"channel_url": "garbage"})
            assert response.status_code == 400
            assert "Invalid YouTube URL" in response.json()["detail"]
        print("✓ /analyze-channel invalid input handling passed")

        print("Testing /find-competitors with missing profile...")
        with patch("app.main.get_cached_channel_profile") as mock_get:
            mock_get.return_value = None
            response = await ac.post("/find-competitors", json={"channel_id": "UC123"})
            assert response.status_code == 400
            assert "Channel profile not found" in response.json()["detail"]
        print("✓ /find-competitors missing profile handling passed")

        print("Testing /search-topic with missing profile...")
        with patch("app.main.get_cached_channel_profile") as mock_get:
            mock_get.return_value = None
            response = await ac.post("/search-topic", json={"channel_id": "UC123", "topic": "test"})
            assert response.status_code == 400
            assert "Channel profile not found" in response.json()["detail"]
        print("✓ /search-topic missing profile handling passed")

if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
        print("\nAll Phase 10 validation tests passed!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nValidation failed: {e}")
        sys.exit(1)
