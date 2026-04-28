"""SQLAlchemy 2.0 async engine + session factory + ORM models.

Mirrors the subset of `infra/sql/01_schema.sql` that Phase 0d touches:
`programs`, `scopes`, `scope_changes`. EV/findings/etc. are owned by other
phases and intentionally NOT modeled here.

Conventions
-----------
* `DATABASE_URL` env var (default: `postgresql+asyncpg://...`); SQLite via
  `sqlite+aiosqlite:///...` is supported for tests.
* `async_sessionmaker(expire_on_commit=False)` so detached objects stay usable
  after commit (matches build plan §Storage).
* `Base(AsyncAttrs, DeclarativeBase)` — enables awaitable lazy attrs.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DEFAULT_DATABASE_URL = "postgresql+asyncpg://bountystrike:bountystrike@localhost:5432/bountystrike"


class Base(AsyncAttrs, DeclarativeBase):
    """Async-aware declarative base."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Program(Base):
    __tablename__ = "programs"

    handle: Mapped[str] = mapped_column(Text, primary_key=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    payout_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    payout_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    bounty_paid_ratio: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    triage_acceptance_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    dup_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    scopes: Mapped[list[Scope]] = relationship(
        "Scope", back_populates="program", cascade="all, delete-orphan"
    )


class Scope(Base):
    __tablename__ = "scopes"
    __table_args__ = (
        UniqueConstraint(
            "program_handle",
            "asset_type",
            "identifier",
            name="uq_scopes_program_asset_identifier",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    program_handle: Mapped[str] = mapped_column(
        Text,
        ForeignKey("programs.handle", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    in_scope: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    program: Mapped[Program] = relationship("Program", back_populates="scopes")


class ScopeChange(Base):
    __tablename__ = "scope_changes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    program_handle: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# Engine + session factory
# ---------------------------------------------------------------------------


def get_database_url() -> str:
    """Return the configured DATABASE_URL or the local Postgres default."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_engine(url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    """Build an `AsyncEngine`. Caller owns disposal."""
    return create_async_engine(url or get_database_url(), echo=echo, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`expire_on_commit=False` so callers can use ORM objects after commit."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


__all__ = [
    "Base",
    "Program",
    "Scope",
    "ScopeChange",
    "create_engine",
    "get_database_url",
    "make_session_factory",
]
