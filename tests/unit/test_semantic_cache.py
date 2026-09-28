from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from rulesgen.infra.semantic_cache import (
    GPTSemanticTranslationCache,
    HashingEmbedding,
    prompt_digest,
)

SCOPE = json.dumps({"table_name": "orders", "targets": ["discount"]})
STORED_PROMPT = "- discount: if quantity is 5 or higher, discount is 10 percent of price"
STORED_RESPONSE = json.dumps(
    [{"target_column": "discount", "rule": 'col("price") * 0.1 if col("quantity") >= 5 else 0'}]
)


def _cache(root: Path, *, threshold: float = 0.82) -> GPTSemanticTranslationCache:
    return GPTSemanticTranslationCache(root_dir=root, similarity_threshold=threshold)


def test_identical_prompt_hits_the_cache(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)

    hit = cache.get(scope_key=SCOPE, prompt_text=STORED_PROMPT)

    assert hit is not None
    assert hit.response_text == STORED_RESPONSE
    assert hit.cache.hit is True


def test_whitespace_only_differences_still_hit(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)

    hit = cache.get(scope_key=SCOPE, prompt_text=f"  {STORED_PROMPT.replace(' ', '   ')}\n")

    assert hit is not None


@pytest.mark.parametrize("threshold", [0.0, 0.82, 0.99])
@pytest.mark.parametrize(
    "prompt",
    [
        "- discount: if quantity is 5 or lower, discount is 10 percent of price",
        "- discount: if quantity is 5 or higher, discount is 10 percent of total",
        "- discount: if quantity is 50 or higher, discount is 90 percent of price",
    ],
)
def test_similar_but_different_prompts_never_reuse_a_translation(
    tmp_path: Path, threshold: float, prompt: str
) -> None:
    embedding = HashingEmbedding()
    stored_vector = embedding.to_embeddings(STORED_PROMPT)
    query_vector = embedding.to_embeddings(prompt)
    # Guard the premise: these prompts are close in embedding space.
    assert float(stored_vector @ query_vector) > 0.8

    cache = _cache(tmp_path, threshold=threshold)
    cache.put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)

    assert cache.get(scope_key=SCOPE, prompt_text=prompt) is None


def test_cache_files_store_prompt_digests_not_prompt_text(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)

    stored_files = list(tmp_path.glob("*.json"))
    assert len(stored_files) == 1
    raw = stored_files[0].read_text(encoding="utf-8")
    assert "quantity is 5 or higher" not in raw
    assert json.loads(raw)[0]["question"] == prompt_digest(STORED_PROMPT)


def test_legacy_cache_files_are_migrated_to_digests(tmp_path: Path) -> None:
    seeding_cache = _cache(tmp_path / "seed")
    seeding_cache.put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)
    seeded_file = next((tmp_path / "seed").glob("*.json"))
    legacy_entries = json.loads(seeded_file.read_text(encoding="utf-8"))
    legacy_entries[0]["question"] = STORED_PROMPT
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    legacy_file = legacy_dir / seeded_file.name
    legacy_file.write_text(json.dumps(legacy_entries), encoding="utf-8")

    cache = _cache(legacy_dir)
    hit = cache.get(scope_key=SCOPE, prompt_text=STORED_PROMPT)

    assert hit is not None
    migrated = legacy_file.read_text(encoding="utf-8")
    assert "quantity is 5 or higher" not in migrated
    assert json.loads(migrated)[0]["question"] == prompt_digest(STORED_PROMPT)


def test_gptcache_debug_logging_is_suppressed() -> None:
    from gptcache.utils.log import gptcache_log

    assert gptcache_log.getEffectiveLevel() >= logging.WARNING
