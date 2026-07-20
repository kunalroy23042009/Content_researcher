"""Database — SQLModel engine, tables, and caching for SQLite/PostgreSQL.

Persists channel profiles, topic searches, users, and API keys.
Supports SQLite for local dev and PostgreSQL for production.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import settings
from app.models import ChannelProfile, ContentResult, TopicInsight

logger = logging.getLogger(__name__)

DB_DIR = Path("data")
DB_PATH = DB_DIR / "cache.db"

_engine = None


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class Channel(SQLModel, table=True):
    """Cached YouTube channel profile."""

    channel_id: str = Field(primary_key=True)
    url: str
    profile_json: str
    analyzed_at: datetime


class CompetitorList(SQLModel, table=True):
    """Cached competitor channel list for a source channel."""

    id: int | None = Field(default=None, primary_key=True)
    channel_id: str = Field(foreign_key="channel.channel_id")
    competitors_json: str
    generated_at: datetime


class TopicSearch(SQLModel, table=True):
    """Cached topic search results and AI insights for a channel."""

    id: int | None = Field(default=None, primary_key=True)
    channel_id: str = Field(foreign_key="channel.channel_id")
    topic: str
    results_json: str
    insight_json: str
    searched_at: datetime


class User(SQLModel, table=True):
    """Registered user for the SaaS."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    plan: str = Field(default="free")  # free, pro, business
    analyses_this_month: int = Field(default=0)
    stripe_customer_id: str | None = Field(default=None)
    created_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApiKey(SQLModel, table=True):
    """API keys for Business plan users."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    key_hash: str = Field(unique=True, index=True)
    label: str = Field(default="default")
    created_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Engine / init
# ---------------------------------------------------------------------------


def _get_engine():
    """Return the shared SQLAlchemy engine (lazy singleton)."""
    global _engine
    if _engine is None:
        db_url = getattr(settings, "DATABASE_URL", "") or f"sqlite:///{DB_PATH}"
        if db_url.startswith("postgres"):
            logger.info("Using PostgreSQL: %s", db_url.split("@")[-1] if "@" in db_url else "configured")
            _engine = create_engine(db_url, pool_pre_ping=True)
        else:
            DB_DIR.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
            )
    return _engine


def init_db() -> None:
    """Create database and all tables if they do not exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(_get_engine())
    logger.info("Database initialized at %s", DB_PATH.resolve())


def reset_engine() -> None:
    """Reset the engine singleton (used in tests)."""
    global _engine
    _engine = None


def get_session():
    """FastAPI dependency that yields a database session."""
    with Session(_get_engine()) as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _is_fresh(timestamp: datetime, max_age_hours: int) -> bool:
    age = _utc_now() - _ensure_aware(timestamp)
    return age < timedelta(hours=max_age_hours)


def _normalize_topic(topic: str) -> str:
    return topic.strip()


def _serialize_profile(profile: ChannelProfile) -> str:
    return profile.model_dump_json()


def _deserialize_profile(data: str) -> ChannelProfile:
    return ChannelProfile.model_validate_json(data)


def _serialize_results(results: list[ContentResult]) -> str:
    return json.dumps([r.model_dump(mode="json") for r in results])


def _deserialize_results(data: str) -> list[ContentResult]:
    payload = json.loads(data)
    return [ContentResult.model_validate(item) for item in payload]


def _serialize_insight(insight: TopicInsight) -> str:
    return insight.model_dump_json()


def _deserialize_insight(data: str) -> TopicInsight:
    return TopicInsight.model_validate_json(data)


def _ensure_channel_row(session: Session, channel_id: str) -> None:
    """Insert a minimal channel row if needed for FK integrity."""
    if session.get(Channel, channel_id) is None:
        session.add(
            Channel(
                channel_id=channel_id,
                url="",
                profile_json="{}",
                analyzed_at=_utc_now(),
            )
        )


# ---------------------------------------------------------------------------
# Channel profile cache
# ---------------------------------------------------------------------------


def get_cached_channel_profile(
    channel_id: str,
    max_age_hours: int = 24,
) -> ChannelProfile | None:
    """Return a cached profile if present and younger than *max_age_hours*."""
    with Session(_get_engine()) as session:
        row = session.get(Channel, channel_id)
        if row is None or not _is_fresh(row.analyzed_at, max_age_hours):
            return None
        return _deserialize_profile(row.profile_json)


def get_cached_channel_profile_by_url(
    url: str,
    max_age_hours: int = 24,
) -> ChannelProfile | None:
    """Return a cached profile looked up by the original channel URL."""
    normalized = url.strip()
    with Session(_get_engine()) as session:
        statement = select(Channel).where(Channel.url == normalized)
        row = session.exec(statement).first()
        if row is None or not _is_fresh(row.analyzed_at, max_age_hours):
            return None
        return _deserialize_profile(row.profile_json)


def save_channel_profile(profile: ChannelProfile, url: str) -> None:
    """Upsert a channel profile into the cache."""
    now = _utc_now()
    with Session(_get_engine()) as session:
        existing = session.get(Channel, profile.channel_id)
        payload = _serialize_profile(profile)
        if existing is None:
            session.add(
                Channel(
                    channel_id=profile.channel_id,
                    url=url.strip(),
                    profile_json=payload,
                    analyzed_at=now,
                )
            )
        else:
            existing.url = url.strip()
            existing.profile_json = payload
            existing.analyzed_at = now
            session.add(existing)
        session.commit()


# ---------------------------------------------------------------------------
# Topic search cache
# ---------------------------------------------------------------------------


def get_cached_topic_search(
    channel_id: str,
    topic: str,
    max_age_hours: int = 24,
) -> tuple[list[ContentResult], TopicInsight] | None:
    """Return cached topic results + insight if present and fresh."""
    normalized_topic = _normalize_topic(topic)
    with Session(_get_engine()) as session:
        statement = (
            select(TopicSearch)
            .where(TopicSearch.channel_id == channel_id)
            .where(TopicSearch.topic == normalized_topic)
            .order_by(TopicSearch.searched_at.desc())  # type: ignore[attr-defined]
        )
        row = session.exec(statement).first()
        if row is None or not _is_fresh(row.searched_at, max_age_hours):
            return None
        return (
            _deserialize_results(row.results_json),
            _deserialize_insight(row.insight_json),
        )


def save_topic_search(
    channel_id: str,
    topic: str,
    results: list[ContentResult],
    insight: TopicInsight,
) -> None:
    """Persist topic search results and AI insights."""
    normalized_topic = _normalize_topic(topic)
    now = _utc_now()
    with Session(_get_engine()) as session:
        _ensure_channel_row(session, channel_id)

        statement = (
            select(TopicSearch)
            .where(TopicSearch.channel_id == channel_id)
            .where(TopicSearch.topic == normalized_topic)
        )
        existing = session.exec(statement).first()
        payload_results = _serialize_results(results)
        payload_insight = _serialize_insight(insight)

        if existing is None:
            session.add(
                TopicSearch(
                    channel_id=channel_id,
                    topic=normalized_topic,
                    results_json=payload_results,
                    insight_json=payload_insight,
                    searched_at=now,
                )
            )
        else:
            existing.results_json = payload_results
            existing.insight_json = payload_insight
            existing.searched_at = now
            session.add(existing)
        session.commit()
