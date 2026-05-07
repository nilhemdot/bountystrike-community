#!/usr/bin/env python3
"""Alpha hunter onboarding (Phase 3 build-plan §10.5 objective: 3-5 hunters).

Creates one ``operators`` row, issues a scope JWT for each program in
``--programs``, and prints quick-start instructions. Reuses
``issue_scope_jwt`` from gen_scope_jwt.py so the JWT shape stays
identical across solo workflows.

Usage:
    python scripts/onboard_hunter.py \\
        --id alice \\
        --name "Alice Hunter" \\
        --programs acme-corp,widget-co \\
        --hosts acme.example.com,widget.example.com \\
        --hours 168

Environment:
    DATABASE_URL  postgresql[+asyncpg]://...   (required)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import asyncpg

# Reuse the existing JWT issuance logic — same key pair, same payload shape.
from gen_scope_jwt import ensure_keys, issue_scope_jwt


def _get_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


SQL_UPSERT_OPERATOR = """
INSERT INTO operators (id, display_name, skill_vector)
VALUES ($1, $2, $3::jsonb)
ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        skill_vector = EXCLUDED.skill_vector
RETURNING id, created_at
"""


async def _create_operator(
    conn: asyncpg.Connection,
    operator_id: str,
    display_name: str,
    skill_vector: dict,
) -> dict:
    row = await conn.fetchrow(
        SQL_UPSERT_OPERATOR,
        operator_id, display_name, json.dumps(skill_vector),
    )
    if row is None:
        raise RuntimeError("operators upsert returned no row")
    return {"id": row["id"], "created_at": row["created_at"].isoformat()}


def _quickstart(operator_id: str, jwts: list[dict]) -> str:
    lines = [
        f"\nOperator '{operator_id}' onboarded.",
        f"Scope JWTs issued ({len(jwts)}):",
    ]
    for entry in jwts:
        lines.append(
            f"  • {entry['program']:<24}  "
            f"jti={entry['jti']}  expires={entry['expires_at']}"
        )
    lines += [
        "",
        "Quick start:",
        "  export DATABASE_URL=postgresql://bs:<password>@127.0.0.1:5432/bountystrike",
        "  export SCOPE_JWT=<one of the tokens above>",
        f"  python scripts/orchestrator.py --program {jwts[0]['program']} \\",
        f"      --operator {operator_id}",
        "",
        "Approval CLI (T2/T3 review):",
        "  python scripts/approve.py list",
        "",
        "Cost audit:",
        f"  python scripts/cost_audit.py --operator {operator_id}",
    ]
    return "\n".join(lines)


async def _main(args: argparse.Namespace) -> int:
    programs = [p.strip() for p in args.programs.split(",") if p.strip()]
    if not programs:
        print("ERROR: --programs requires at least one handle", file=sys.stderr)
        return 2

    hosts_per_program: dict[str, list[str]] = {}
    if args.hosts:
        host_list = [h.strip() for h in args.hosts.split(",") if h.strip()]
        # Pair hosts with programs by index; missing hosts default to a
        # placeholder so the JWT still validates structurally.
        for idx, prog in enumerate(programs):
            hosts_per_program[prog] = (
                [host_list[idx]] if idx < len(host_list) else [f"{prog}.example.com"]
            )
    else:
        for prog in programs:
            hosts_per_program[prog] = []

    wildcards = [w.strip() for w in args.wildcards.split(",") if w.strip()]
    # Wildcards apply to every program in this onboarding call — operator
    # workflows typically run one program at a time with several
    # wildcards (e.g. `*.shopify.com,*.shopify.io`), so paired-by-index
    # would be the wrong mental model here.

    # Backstop: if neither --hosts nor --wildcards was supplied for a
    # program, fall back to the placeholder host so the JWT still
    # validates structurally without granting any real scope.
    for prog in programs:
        if not hosts_per_program[prog] and not wildcards:
            hosts_per_program[prog] = [f"{prog}.example.com"]

    skill_vector: dict = {}
    if args.skills:
        for kv in args.skills.split(","):
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            try:
                skill_vector[k.strip()] = float(v.strip())
            except ValueError:
                print(f"WARN: skipping non-numeric skill '{kv}'", file=sys.stderr)

    private_pem, _ = ensure_keys(force=False)

    conn = await asyncpg.connect(_get_dsn())
    try:
        op_row = await _create_operator(conn, args.id, args.name, skill_vector)
    finally:
        await conn.close()

    print(f"operators row: id={op_row['id']} created_at={op_row['created_at']}")

    jwt_records: list[dict] = []
    for prog in programs:
        result = issue_scope_jwt(
            private_pem=private_pem,
            operator_id=args.id,
            program_handle=prog,
            platform=args.platform,
            wildcards=wildcards,
            exact_hosts=hosts_per_program[prog],
            default_rps=args.rps,
            expiry_hours=args.hours,
        )
        jwt_records.append({
            "program": prog,
            "jti": result["jti"],
            "expires_at": result["expires_at"],
            "token": result["token"],
        })

    if args.json:
        print(json.dumps({
            "operator": op_row,
            "jwts": jwt_records,
        }, indent=2))
    else:
        for entry in jwt_records:
            print(f"\n=== {entry['program']} ===")
            print(entry["token"])
        print(_quickstart(args.id, jwt_records))

    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="onboard_hunter",
        description="Phase 3: register an alpha hunter + issue scope JWTs",
    )
    p.add_argument("--id", required=True, help="operator slug (e.g. alice)")
    p.add_argument("--name", required=True, help="display name")
    p.add_argument("--programs", required=True,
                   help="comma-separated program handles")
    p.add_argument("--hosts", default="",
                   help="comma-separated exact hosts (paired with programs by index)")
    p.add_argument("--wildcards", default="",
                   help="comma-separated wildcard targets (e.g. '*.shopify.com'); "
                        "applied to every program in --programs")
    p.add_argument("--platform", default="hackerone")
    p.add_argument("--hours", type=float, default=168.0,
                   help="JWT expiry (default 168h = 7 days, max 168)")
    p.add_argument("--rps", type=int, default=5, help="rate limit per second")
    p.add_argument("--skills", default="",
                   help="skill_vector entries 'web=0.9,api=0.7'")
    p.add_argument("--json", action="store_true", help="emit JSON instead of human output")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
