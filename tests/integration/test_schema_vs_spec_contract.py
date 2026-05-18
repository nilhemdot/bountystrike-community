"""F2 — schema-vs-spec contract test.

Purpose: catch the same drift class that produced Bug-2 in
`docs/signoffs/phase1_signoff.md` Round 5 (agent specs referenced
``findings.raw_finding`` before any migration created the column).

Mechanism: extract every ``` ```sql ``` fence from
``.claude/agents/*.md``, normalise ``:name`` placeholders to ``$N``
positional parameters, and call :meth:`asyncpg.Connection.prepare` on
each statement against a Postgres database with migrations 00–05
applied. ``prepare`` runs Postgres's Parse phase, which resolves every
table and column referenced by the statement; if any reference is
missing or mistyped, prepare raises and the test fails.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_schema_vs_spec_contract.py -v

The DSN must point to a database with migrations 00–05 already
applied. The test never writes to the database — every statement is
parsed, never executed.

Helpers in this module (``_extract_sql_blocks``, ``_split_statements``,
``_substitute_named_params``, ``_is_executable_sql``) are independently
unit-tested at the bottom of the file so the extractor is verified
without needing a live Postgres.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)


# ---------------------------------------------------------------------------
# Helpers — pure functions, independently unit-tested below.
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"^```sql\s*$\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
# Match :name placeholders but skip ::cast and string-literal contents.
_NAMED_PARAM_RE = re.compile(r"(?<![:\w]):([a-zA-Z_][a-zA-Z0-9_]*)")
_DML_KEYWORDS = ("select", "insert", "update", "delete", "with")


def _extract_sql_blocks(md_text: str) -> list[str]:
    """Return the inner text of every ```sql ... ``` fence in *md_text*."""
    return [m.group(1) for m in _FENCE_RE.finditer(md_text)]


def _strip_string_literals_and_comments(sql: str) -> str:
    """Return a length-preserving mask of *sql* in which single-quoted
    string literals and ``--`` line comments have been replaced by
    spaces. Length preservation is critical: callers index back into
    the original ``sql`` using offsets computed against the mask, so
    every character must keep its original position."""
    out: list[str] = list(sql)
    i = 0
    n = len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            # Quote stays visible so split/substitute can see the
            # literal boundary, but the body is blanked.
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        # Escaped quote — blank both, keep walking.
                        out[j] = " "
                        out[j + 1] = " "
                        j += 2
                        continue
                    break
                out[j] = " " if sql[j] != "\n" else "\n"
                j += 1
            i = j + 1
            continue
        if c == "-" and i + 1 < n and sql[i + 1] == "-":
            # Blank the comment body up to (but excluding) the newline.
            j = i
            while j < n and sql[j] != "\n":
                out[j] = " "
                j += 1
            i = j
            continue
        i += 1
    return "".join(out)


def _split_statements(sql: str) -> list[str]:
    """Split *sql* into statements at top-level semicolons.

    String literals and ``--`` comments are masked first so a semicolon
    inside ``'a;b'`` or after a ``--`` comment doesn't split.
    """
    masked = _strip_string_literals_and_comments(sql)
    splits = [0]
    for i, ch in enumerate(masked):
        if ch == ";":
            splits.append(i + 1)
    splits.append(len(sql))
    statements: list[str] = []
    for a, b in zip(splits, splits[1:]):
        chunk = sql[a:b].strip().rstrip(";").strip()
        if chunk:
            statements.append(chunk)
    return statements


def _substitute_named_params(sql: str) -> tuple[str, list[str]]:
    """Replace ``:name`` placeholders with positional ``$N``.

    Repeated occurrences of the same name share an index. Returns
    ``(rewritten_sql, names_in_order)``.
    """
    masked = _strip_string_literals_and_comments(sql)
    name_to_index: dict[str, int] = {}
    ordered_names: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in name_to_index:
            ordered_names.append(name)
            name_to_index[name] = len(ordered_names)
        return f"${name_to_index[name]}"

    # Apply replacement on a per-character basis driven by the masked copy
    # so we never substitute inside literals/comments.
    out: list[str] = []
    i = 0
    while i < len(sql):
        m = _NAMED_PARAM_RE.match(masked, i)
        if m is not None and m.start() == i:
            out.append(_replace(m))
            i = m.end()
        else:
            out.append(sql[i])
            i += 1
    return "".join(out), ordered_names


def _is_executable_sql(sql: str) -> bool:
    """Return True iff *sql* contains a recognisable DML keyword.

    Skips fences that hold column listings or commentary rather than a
    statement (e.g. validator.md's first fence enumerates findings
    columns inside a code block).
    """
    masked = _strip_string_literals_and_comments(sql).lower()
    return any(re.search(rf"\b{kw}\b", masked) for kw in _DML_KEYWORDS)


def _agent_statements() -> list[tuple[str, int, str]]:
    """Walk every agent spec and yield ``(spec_path, fence_index, statement)``
    triples for each executable statement.

    ``fence_index`` is the 0-indexed position of the ```sql``` fence
    within the markdown file — useful for pinpointing failures.
    """
    triples: list[tuple[str, int, str]] = []
    for md_path in sorted(AGENTS_DIR.glob("*.md")):
        text = md_path.read_text()
        for fence_idx, sql in enumerate(_extract_sql_blocks(text)):
            for stmt in _split_statements(sql):
                if _is_executable_sql(stmt):
                    triples.append((str(md_path.relative_to(REPO_ROOT)), fence_idx, stmt))
    return triples


# ---------------------------------------------------------------------------
# Integration — Parse every statement against the live schema.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "spec,fence_idx,statement",
    _agent_statements(),
    ids=lambda v: (
        v if isinstance(v, str) and "/" in v
        else (str(v) if not isinstance(v, str) else v[:60].replace("\n", " "))
    ),
)
async def test_agent_spec_sql_parses_against_live_schema(
    spec: str, fence_idx: int, statement: str
) -> None:
    """Every executable statement in every agent spec must parse against
    the migrated schema. Failure surfaces drift before it bites
    production (the Bug-2 detection mechanism)."""
    import asyncpg  # local import — keeps unit tests below importable
                    # without asyncpg installed in dev-only environments.

    rewritten, _ = _substitute_named_params(statement)
    conn = await asyncpg.connect(_DSN)
    try:
        try:
            await conn.prepare(rewritten)
        except (
            asyncpg.UndefinedColumnError,
            asyncpg.UndefinedTableError,
            asyncpg.UndefinedObjectError,
            asyncpg.PostgresSyntaxError,
        ) as exc:
            pytest.fail(
                f"\nSpec drift in {spec} (fence #{fence_idx}):\n"
                f"  {type(exc).__name__}: {exc}\n"
                f"--- statement ---\n{statement}\n"
                f"--- rewritten ---\n{rewritten}\n"
            )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Unit tests — extractor / normaliser. No Postgres required.
# ---------------------------------------------------------------------------


def test_extract_sql_blocks_returns_each_fence_in_order() -> None:
    md = (
        "header\n"
        "```sql\n"
        "SELECT 1;\n"
        "```\n"
        "prose\n"
        "```sql\n"
        "INSERT INTO t VALUES (1);\n"
        "```\n"
    )
    blocks = _extract_sql_blocks(md)
    assert len(blocks) == 2
    assert "SELECT 1" in blocks[0]
    assert "INSERT INTO t" in blocks[1]


def test_extract_sql_blocks_ignores_other_fence_languages() -> None:
    md = (
        "```python\nprint('hi')\n```\n"
        "```sql\nSELECT 1;\n```\n"
        "```\nplain fence\n```\n"
    )
    assert _extract_sql_blocks(md) == ["SELECT 1;\n"]


def test_split_statements_handles_multiple_semicolons() -> None:
    sql = "INSERT INTO t VALUES (1);\nUPDATE t SET x = 2;"
    assert _split_statements(sql) == [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x = 2",
    ]


def test_split_statements_ignores_semicolons_in_strings() -> None:
    sql = "INSERT INTO t VALUES ('a;b'); UPDATE t SET x = 'c;d';"
    out = _split_statements(sql)
    assert len(out) == 2
    assert "'a;b'" in out[0]
    assert "'c;d'" in out[1]


def test_split_statements_ignores_semicolons_in_comments() -> None:
    sql = "INSERT INTO t VALUES (1); -- trailing; comment\nSELECT 2;"
    out = _split_statements(sql)
    assert len(out) == 2
    assert "INSERT INTO t" in out[0]
    assert "SELECT 2" in out[1]


def test_substitute_named_params_assigns_unique_indices() -> None:
    sql = "SELECT * FROM t WHERE a = :x AND b = :y"
    rewritten, names = _substitute_named_params(sql)
    assert rewritten == "SELECT * FROM t WHERE a = $1 AND b = $2"
    assert names == ["x", "y"]


def test_substitute_named_params_reuses_index_for_repeated_name() -> None:
    sql = "UPDATE t SET a = :id WHERE id = :id RETURNING :id"
    rewritten, names = _substitute_named_params(sql)
    assert rewritten == "UPDATE t SET a = $1 WHERE id = $1 RETURNING $1"
    assert names == ["id"]


def test_substitute_named_params_skips_double_colon_casts() -> None:
    sql = "SELECT now()::text, :flag"
    rewritten, names = _substitute_named_params(sql)
    assert rewritten == "SELECT now()::text, $1"
    assert names == ["flag"]


def test_substitute_named_params_skips_inside_string_literal() -> None:
    sql = "SELECT ':not_a_param', :real_one"
    rewritten, names = _substitute_named_params(sql)
    assert rewritten == "SELECT ':not_a_param', $1"
    assert names == ["real_one"]


def test_is_executable_sql_recognises_dml() -> None:
    assert _is_executable_sql("SELECT 1")
    assert _is_executable_sql("insert into t values (1)")
    assert _is_executable_sql("WITH x AS (SELECT 1) SELECT * FROM x")
    assert _is_executable_sql("UPDATE t SET a = 1")
    assert _is_executable_sql("DELETE FROM t")


def test_is_executable_sql_rejects_comment_only_block() -> None:
    block = (
        "-- Relevant columns from findings table\n"
        "id                UUID\n"
        "job_id            UUID        -- FK to scan_jobs\n"
    )
    assert not _is_executable_sql(block)


def test_is_executable_sql_rejects_empty_string() -> None:
    assert not _is_executable_sql("")
    assert not _is_executable_sql("   \n  ")


def test_agent_statements_finds_at_least_one_statement_per_known_spec() -> None:
    """Sanity: every agent spec we know to contain SQL produces at least
    one executable statement after extraction. Guards against a regex
    regression that silently drops everything."""
    triples = _agent_statements()
    specs_with_sql = {t[0] for t in triples}
    expected_specs = {
        ".claude/agents/recon.md",
        ".claude/agents/scanner-agent.md",
        ".claude/agents/exploit-agent.md",
        ".claude/agents/validator.md",
        ".claude/agents/reporter.md",
        ".claude/agents/ai-vuln-hunter.md",
        ".claude/agents/cloud-recon-agent.md",
    }
    missing = expected_specs - specs_with_sql
    assert not missing, f"extractor produced no statements for: {missing}"
