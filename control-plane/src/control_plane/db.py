"""Deprecated compat shim — re-exports from `control_plane.infrastructure.database`.

The async engine, sessionmaker, Base, and ORM models (Program, Scope,
ScopeChange) live in the infrastructure layer. This module is kept only to
avoid breaking existing imports in the scope_management domain services and
their tests. New code should import from
`control_plane.infrastructure.database` directly.
"""

from __future__ import annotations

from .infrastructure.database import (
    DEFAULT_DATABASE_URL,
    Base,
    Program,
    Scope,
    ScopeChange,
    create_engine,
    get_database_url,
    make_session_factory,
)

__all__ = [
    "DEFAULT_DATABASE_URL",
    "Base",
    "Program",
    "Scope",
    "ScopeChange",
    "create_engine",
    "get_database_url",
    "make_session_factory",
]
