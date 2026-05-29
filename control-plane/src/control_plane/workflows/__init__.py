# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hatchet v1 durable-execution workflows for BountyStrike (plan 01-02).

The shared ``hatchet`` client, task definitions, and the worker entry point all
live here. Importing the client from a single module keeps the SDK client
instantiated exactly once across the worker process and any trigger call site.
"""
