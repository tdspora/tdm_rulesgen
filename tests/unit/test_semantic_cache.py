from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TextIO

import pytest

from rulesgen.infra import semantic_cache
from rulesgen.infra.semantic_cache import (
    QUESTION_DIGEST_FIELD,
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


@pytest.mark.parametrize(
    ("stored", "queried"),
    [
        ('- status: set to "on hold"', '- status: set to "on  hold"'),
        (STORED_PROMPT, f"  {STORED_PROMPT}\n"),
    ],
)
def test_prompts_that_differ_only_in_whitespace_do_not_share_an_entry(
    tmp_path: Path, stored: str, queried: str
) -> None:
    cache = _cache(tmp_path, threshold=0.0)
    cache.put(scope_key=SCOPE, prompt_text=stored, response_text=STORED_RESPONSE)

    assert cache.get(scope_key=SCOPE, prompt_text=queried) is None
    assert cache.get(scope_key=SCOPE, prompt_text=stored) is not None


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
    [entry] = json.loads(raw)
    assert entry[QUESTION_DIGEST_FIELD] == prompt_digest(STORED_PROMPT)
    assert "question" not in entry


def test_prompts_that_look_like_digests_are_hashed_too(tmp_path: Path) -> None:
    cache = _cache(tmp_path, threshold=0.0)
    # Stored verbatim, this prompt would be the entry for STORED_PROMPT.
    cache.put(scope_key=SCOPE, prompt_text=prompt_digest(STORED_PROMPT), response_text='"planted"')

    assert cache.get(scope_key=SCOPE, prompt_text=STORED_PROMPT) is None


def _write_legacy_cache_file(root: Path, seed_root: Path) -> Path:
    """Write a cache file in the format of earlier versions, with the prompt text."""
    _cache(seed_root).put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)
    seeded_file = next(seed_root.glob("*.json"))
    legacy_entries = json.loads(seeded_file.read_text(encoding="utf-8"))
    for entry in legacy_entries:
        del entry[QUESTION_DIGEST_FIELD]
        entry["question"] = STORED_PROMPT
    root.mkdir(parents=True, exist_ok=True)
    legacy_file = root / seeded_file.name
    legacy_file.write_text(json.dumps(legacy_entries), encoding="utf-8")
    return legacy_file


def _assert_migrated(legacy_file: Path) -> None:
    migrated = legacy_file.read_text(encoding="utf-8")
    assert "quantity is 5 or higher" not in migrated
    [entry] = json.loads(migrated)
    assert entry[QUESTION_DIGEST_FIELD] == prompt_digest(STORED_PROMPT)
    assert "question" not in entry


def test_legacy_cache_files_are_migrated_when_the_cache_starts(tmp_path: Path) -> None:
    legacy_file = _write_legacy_cache_file(tmp_path / "legacy", tmp_path / "seed")

    cache = _cache(tmp_path / "legacy")

    # Converted before its scope is used.
    _assert_migrated(legacy_file)
    hit = cache.get(scope_key=SCOPE, prompt_text=STORED_PROMPT)
    assert hit is not None
    assert hit.response_text == STORED_RESPONSE


def test_legacy_cache_files_added_later_are_migrated_when_their_scope_is_used(
    tmp_path: Path,
) -> None:
    cache = _cache(tmp_path / "legacy")
    legacy_file = _write_legacy_cache_file(tmp_path / "legacy", tmp_path / "seed")

    hit = cache.get(scope_key=SCOPE, prompt_text=STORED_PROMPT)

    assert hit is not None
    _assert_migrated(legacy_file)


def test_unreadable_cache_files_are_reported_and_left_in_place(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken_file = tmp_path / "broken.json"
    broken_file.write_text('[{"question": "quantity is 5 or higher"', encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="rulesgen.infra.semantic_cache"):
        _cache(tmp_path)

    assert "broken.json" in caplog.text
    assert "quantity" not in caplog.text
    assert broken_file.read_text(encoding="utf-8") == '[{"question": "quantity is 5 or higher"'


def test_failed_cache_writes_keep_the_previous_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = _cache(tmp_path)
    cache.put(scope_key=SCOPE, prompt_text=STORED_PROMPT, response_text=STORED_RESPONSE)
    [cache_file] = tmp_path.glob("*.json")
    before = cache_file.read_text(encoding="utf-8")

    def failing_dump(payload: object, stream: TextIO, **kwargs: object) -> None:
        del payload, kwargs
        stream.write('[{"id": 1, ')
        raise OSError("No space left on device")

    monkeypatch.setattr(semantic_cache.json, "dump", failing_dump)

    with pytest.raises(OSError, match="No space left"):
        cache.put(scope_key=SCOPE, prompt_text="- total: price plus tax", response_text="[]")

    assert cache_file.read_text(encoding="utf-8") == before
    assert sorted(path.name for path in tmp_path.iterdir()) == [cache_file.name]


def test_gptcache_debug_logging_is_suppressed() -> None:
    from gptcache.utils.log import gptcache_log

    assert gptcache_log.getEffectiveLevel() >= logging.WARNING
