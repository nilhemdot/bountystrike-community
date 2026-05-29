# SPDX-License-Identifier: AGPL-3.0-or-later

"""Infrastructure layer — shared adapters across bounded contexts.

Holds cross-cutting persistence concerns (engine, sessionmaker, ORM models
shared between domains). Domain code imports value objects/aggregates;
infrastructure imports keep ORM mapping outside the domain boundary.
"""
