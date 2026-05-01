"""Phase 2 §10.4 last exit criterion — semantic-dedup recall ≥ 0.90 over a
1000-finding test set with known duplicate pairs.

TDD structure:
  1. Fixture generator produces N findings with K labelled duplicate pairs
     (the ground truth) — purely deterministic, no LLM in the loop.
  2. Recall calculator turns (predictions, ground_truth) into a recall
     number, exercising the math without any embedding I/O.
  3. End-to-end runner glues a (pluggable) embedder to the dedup-mcp's
     ``_check_semantic_duplicate_impl`` and measures recall.

The end-to-end recall against the live OpenAI embedder is opt-in
(``RUN_DEDUP_RECALL=1`` + ``OPENAI_API_KEY``). Unit tests exercise the
pipeline with a deterministic ``BagOfWordsEmbedder`` that produces real
1536-dim cosine-comparable vectors without any network call, so CI can
sanity-check the full plumbing without API spend.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import pytest


# ---------------------------------------------------------------------------
# Step 1 — Fixture generator (RED first)
# ---------------------------------------------------------------------------


def test_fixture_generator_produces_requested_count() -> None:
    """generate_corpus(n=1000, dup_pairs=100) → 1000 findings, 100 labelled pairs.

    A "duplicate pair" is two findings with the same ``dup_group_id``;
    every other finding has a unique ``dup_group_id``. The generator
    exposes both the rows and the ground-truth pair list.
    """
    from dedup_mcp.recall_fixture import generate_corpus

    corpus = generate_corpus(n=1000, dup_pairs=100, seed=42)
    assert corpus.total == 1000
    assert len(corpus.findings) == 1000
    assert len(corpus.dup_pairs) == 100


def test_fixture_pair_membership_is_consistent() -> None:
    """Every dup_pair (a, b) must satisfy: both findings exist + share a group."""
    from dedup_mcp.recall_fixture import generate_corpus

    corpus = generate_corpus(n=200, dup_pairs=20, seed=42)
    by_id = {f.id: f for f in corpus.findings}
    for a, b in corpus.dup_pairs:
        assert a in by_id and b in by_id
        assert by_id[a].dup_group_id == by_id[b].dup_group_id
        assert by_id[a].id != by_id[b].id


def test_fixture_non_pair_findings_have_unique_groups() -> None:
    """Findings outside any labelled pair have ``dup_group_id`` unique to them.

    Without this, the generator could accidentally bake in extra duplicates
    the recall test does not expect, producing inflated TPRs.
    """
    from dedup_mcp.recall_fixture import generate_corpus

    corpus = generate_corpus(n=100, dup_pairs=10, seed=42)
    paired_ids: set[str] = set()
    for a, b in corpus.dup_pairs:
        paired_ids.add(a)
        paired_ids.add(b)
    singletons = [f for f in corpus.findings if f.id not in paired_ids]
    groups = [f.dup_group_id for f in singletons]
    assert len(groups) == len(set(groups))


def test_fixture_paired_findings_have_distinct_text() -> None:
    """Duplicate-pair members must have NON-IDENTICAL text bodies.

    If both members of a pair were textually identical, the cosine
    similarity would be 1.0 trivially. The generator's job is to mutate
    one member so the pair is *semantically* a duplicate but not
    *lexically* identical — that's the realistic case the dedup tier
    must catch.
    """
    from dedup_mcp.recall_fixture import generate_corpus

    corpus = generate_corpus(n=100, dup_pairs=10, seed=42)
    by_id = {f.id: f for f in corpus.findings}
    for a, b in corpus.dup_pairs:
        text_a = by_id[a].title + by_id[a].description
        text_b = by_id[b].title + by_id[b].description
        assert text_a != text_b


def test_fixture_seed_makes_run_deterministic() -> None:
    """Two calls with the same seed produce identical corpora — required so
    a CI failure can be reproduced exactly without relitigating the inputs."""
    from dedup_mcp.recall_fixture import generate_corpus

    a = generate_corpus(n=50, dup_pairs=5, seed=99)
    b = generate_corpus(n=50, dup_pairs=5, seed=99)
    assert [f.id for f in a.findings] == [f.id for f in b.findings]
    assert [(f.title, f.description) for f in a.findings] == [
        (f.title, f.description) for f in b.findings
    ]
    assert a.dup_pairs == b.dup_pairs


def test_fixture_rejects_oversized_pair_count() -> None:
    """K > N/2 is impossible (each pair consumes 2 distinct findings)."""
    from dedup_mcp.recall_fixture import generate_corpus

    with pytest.raises(ValueError):
        generate_corpus(n=10, dup_pairs=6, seed=1)


# ---------------------------------------------------------------------------
# Step 2 — Recall calculator (RED next)
# ---------------------------------------------------------------------------


def test_recall_perfect_score() -> None:
    """All 5 known pairs detected → recall = 1.0."""
    from dedup_mcp.recall_fixture import compute_recall

    truth: Iterable[tuple[str, str]] = [
        ("a", "b"), ("c", "d"), ("e", "f"), ("g", "h"), ("i", "j"),
    ]
    predicted = {frozenset({a, b}) for a, b in truth}
    assert compute_recall(predicted, truth) == 1.0


def test_recall_zero_score() -> None:
    """No predictions → recall = 0.0."""
    from dedup_mcp.recall_fixture import compute_recall

    truth = [("a", "b"), ("c", "d")]
    assert compute_recall(set(), truth) == 0.0


def test_recall_partial_score() -> None:
    """3 of 4 known pairs predicted → recall = 0.75."""
    from dedup_mcp.recall_fixture import compute_recall

    truth = [("a", "b"), ("c", "d"), ("e", "f"), ("g", "h")]
    predicted = {frozenset({"a", "b"}), frozenset({"c", "d"}), frozenset({"e", "f"})}
    assert compute_recall(predicted, truth) == 0.75


def test_recall_false_positives_dont_affect_recall() -> None:
    """Recall measures TP / (TP + FN). Predicting extra pairs that aren't
    in the truth set must not change the recall number — the gate is
    asking ``did we catch the real dups?``, not ``did we predict cleanly?``.
    Precision is a separate measurement that this corpus does not gate
    (Phase 2 §10.4 cites recall only)."""
    from dedup_mcp.recall_fixture import compute_recall

    truth = [("a", "b")]
    predicted = {frozenset({"a", "b"}), frozenset({"x", "y"})}
    assert compute_recall(predicted, truth) == 1.0


def test_recall_pair_order_does_not_matter() -> None:
    """Predicting ``{b, a}`` is the same as ``{a, b}`` — recall calc
    canonicalises the pair set."""
    from dedup_mcp.recall_fixture import compute_recall

    truth = [("a", "b")]
    predicted = {frozenset({"b", "a"})}
    assert compute_recall(predicted, truth) == 1.0


def test_recall_empty_truth_returns_zero() -> None:
    """Avoid the 0/0 divide-by-zero when nothing was labelled."""
    from dedup_mcp.recall_fixture import compute_recall

    assert compute_recall({frozenset({"a", "b"})}, []) == 0.0


# ---------------------------------------------------------------------------
# Step 3 — End-to-end runner over a fake embedder (RED last)
# ---------------------------------------------------------------------------


def test_bag_of_words_embedder_returns_dim_1536() -> None:
    """The deterministic embedder's output dimensions must match the
    schema (``vector(1536)`` in infra/sql/01_schema.sql:169)."""
    from dedup_mcp.embedding import EMBEDDING_DIM
    from dedup_mcp.recall_fixture import BagOfWordsEmbedder

    emb = BagOfWordsEmbedder()
    import asyncio
    vec = asyncio.run(emb.embed("hello world"))
    assert len(vec) == EMBEDDING_DIM


def test_bag_of_words_embedder_similar_text_high_cosine() -> None:
    """Two finding-length paraphrases produce cosine ≥ 0.85 (T2 tier).

    Bag-of-words cosine is monotonic in shared-token mass; on short
    inputs (~6 tokens) a single distinct word per side drops cosine
    below 0.85 — that's the embedder's nature, not a bug. Realistic
    finding bodies are multi-sentence, so the appropriate unit-test
    input is two finding-length descriptions that differ by synonym
    substitution + word reorder. This test fixes the floor at the
    same cosine the production tier (0.85) classifies as ``t2``.
    """
    import asyncio

    from dedup_mcp.recall_fixture import BagOfWordsEmbedder, cosine_similarity

    text_a = (
        "Reflected XSS in /search q parameter. "
        "User-supplied q value is rendered into the page response without "
        "HTML encoding. Browser executes injected script when the /search "
        "endpoint is loaded. Cookie session can be stolen via crafted payload."
    )
    text_b = (
        "Reflected XSS in /search q parameter. "
        "Cookie session may be stolen via injected payload. "
        "User-supplied q input is rendered into the page output without "
        "HTML encoding. Browser executes injected script when the /search "
        "endpoint is loaded."
    )
    emb = BagOfWordsEmbedder()
    a = asyncio.run(emb.embed(text_a))
    b = asyncio.run(emb.embed(text_b))
    assert cosine_similarity(a, b) >= 0.85


def test_bag_of_words_embedder_distinct_text_low_cosine() -> None:
    """Two unrelated texts produce cosine similarity well below the
    display threshold (0.75). Ensures the fake embedder doesn't lump
    everything together."""
    import asyncio

    from dedup_mcp.recall_fixture import BagOfWordsEmbedder, cosine_similarity

    emb = BagOfWordsEmbedder()
    a = asyncio.run(emb.embed("reflected xss in search parameter"))
    b = asyncio.run(emb.embed("aws iam privilege escalation via lambda role"))
    assert cosine_similarity(a, b) < 0.5


async def test_runner_meets_recall_gate_with_fake_embedder() -> None:
    """Full end-to-end with a fake embedder: feed the 1000-row corpus
    through ``run_recall_measurement`` and assert recall ≥ 0.90 — the
    Phase 2 §10.4 exit criterion.

    A pass here proves the pipeline shape is correct; live-OpenAI
    measurement against the same corpus is the ``RUN_DEDUP_RECALL=1``
    opt-in test below."""
    from dedup_mcp.recall_fixture import (
        BagOfWordsEmbedder,
        generate_corpus,
        run_recall_measurement,
    )

    corpus = generate_corpus(n=1000, dup_pairs=100, seed=42)
    embedder = BagOfWordsEmbedder()
    report = await run_recall_measurement(corpus, embedder)
    assert report.recall >= 0.90, (
        f"recall {report.recall:.3f} below 0.90 gate; "
        f"tp={report.true_positives} fn={report.false_negatives} "
        f"truth={len(corpus.dup_pairs)}"
    )


@pytest.mark.skipif(
    os.environ.get("RUN_DEDUP_RECALL") != "1",
    reason="opt-in: set RUN_DEDUP_RECALL=1 + OPENAI_API_KEY for live recall",
)
async def test_runner_meets_recall_gate_with_live_openai() -> None:
    """Live-OpenAI recall measurement — Phase 2 §10.4 exit criterion.

    Cost: 1000 × text-embedding-3-large embeddings ≈ $0.0001/1K tokens
    × ~30 tokens/finding ≈ $0.003 for the full run. Negligible, but
    gated behind RUN_DEDUP_RECALL=1 so CI doesn't burn the budget on
    every push.
    """
    from dedup_mcp.embedding import OpenAIEmbedder
    from dedup_mcp.recall_fixture import generate_corpus, run_recall_measurement

    corpus = generate_corpus(n=1000, dup_pairs=100, seed=42)
    embedder = OpenAIEmbedder()
    report = await run_recall_measurement(corpus, embedder)
    assert report.recall >= 0.90, (
        f"live OpenAI recall {report.recall:.3f} below 0.90 gate; "
        f"tp={report.true_positives} fn={report.false_negatives}"
    )
