from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Final, Protocol

import numpy as np

if TYPE_CHECKING:
    gptcache_log: logging.Logger

    class Cache:
        def init(self, **kwargs: Any) -> None: ...

        def flush(self) -> None: ...

    class Config:
        def __init__(
            self,
            *,
            similarity_threshold: float,
            enable_token_counter: bool,
        ) -> None: ...

    class CacheData:
        def __init__(
            self,
            *,
            question: str,
            answers: str,
            embedding_data: np.ndarray[Any, Any],
        ) -> None: ...

    class BaseEmbedding(Protocol):
        @property
        def dimension(self) -> int: ...

        def to_embeddings(self, data: Any, **kwargs: Any) -> np.ndarray[Any, Any]: ...

    class DataManager(Protocol):
        def flush(self) -> None: ...

    class SearchDistanceEvaluation:
        def __init__(self, *, max_distance: float) -> None: ...

        def evaluation(
            self, src_dict: dict[str, Any], cache_dict: dict[str, Any], **kwargs: Any
        ) -> float: ...

        def range(self) -> tuple[float, float]: ...

    def get_prompt(data: Any, **kwargs: Any) -> str: ...

    def gptcache_get(
        prompt: str,
        *,
        cache_obj: Cache,
        hit_callback: Any | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def gptcache_put(
        prompt: str,
        response: str,
        *,
        cache_obj: Cache,
        **kwargs: Any,
    ) -> None: ...
else:
    from gptcache import Cache, Config  # type: ignore[import-untyped]
    from gptcache.adapter.api import get as gptcache_get  # type: ignore[import-untyped]
    from gptcache.adapter.api import put as gptcache_put  # type: ignore[import-untyped]
    from gptcache.embedding.base import BaseEmbedding  # type: ignore[import-untyped]
    from gptcache.manager.data_manager import DataManager  # type: ignore[import-untyped]
    from gptcache.manager.scalar_data.base import CacheData  # type: ignore[import-untyped]
    from gptcache.processor.pre import get_prompt  # type: ignore[import-untyped]
    from gptcache.similarity_evaluation.distance import (  # type: ignore[import-untyped]
        SearchDistanceEvaluation,
    )
    from gptcache.utils.log import gptcache_log  # type: ignore[import-untyped]

from rulesgen.domain.models import CacheInsight

# GPTCache logs the user prompt and the cached question at DEBUG level. Prompts
# can carry customer data and logs must stay data-free at every level.
gptcache_log.setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

QUESTION_DIGEST_FIELD: Final = "question_sha256"
"""Cache entry field that holds the digest of the prompt the entry was stored for."""

_LEGACY_QUESTION_FIELD: Final = "question"
"""Cache entry field in which earlier versions stored the prompt text itself."""


def prompt_digest(prompt_text: str) -> str:
    """SHA-256 digest of the exact prompt text.

    Cache entries store this digest instead of the prompt text, and a lookup only
    hits entries whose digest equals the digest of the new prompt. The text is not
    normalized, because whitespace inside a quoted value can change a rule.
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


def migrate_cache_files(root_dir: Path) -> None:
    """Replace the prompt text in cache files written by earlier versions.

    A file is also converted when its scope is next used, but a scope that is
    never used again would otherwise keep its prompt text on disk. Files that
    cannot be read are left in place and reported.
    """
    for path in sorted(root_dir.glob("*.json")):
        try:
            entries, migrated = _read_entries(path)
        except (OSError, ValueError):
            logger.warning("Skipped unreadable semantic-cache file %s.", path.name)
            continue
        if migrated:
            _write_entries(path, entries)


def _read_entries(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Read a cache file and whether any entry had to be converted to a digest."""
    if not path.exists():
        return [], False
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return [], False
    entries: list[dict[str, Any]] = []
    migrated = False
    for item in payload:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        if _LEGACY_QUESTION_FIELD in entry:
            question = entry.pop(_LEGACY_QUESTION_FIELD)
            entry.setdefault(QUESTION_DIGEST_FIELD, prompt_digest(str(question)))
            migrated = True
        entries.append(entry)
    return entries, migrated


def _write_entries(path: Path, entries: list[dict[str, Any]]) -> None:
    """Replace a cache file in one step, so a failed write never leaves it truncated."""
    handle, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(entries, stream, indent=2, sort_keys=True)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


@dataclass(slots=True)
class SemanticCacheHit:
    response_text: str
    cache: CacheInsight


class HashingEmbedding(BaseEmbedding):
    def __init__(self, *, dimension: int = 256) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def to_embeddings(self, data: Any, **kwargs: Any) -> np.ndarray[Any, Any]:
        del kwargs
        text = str(data).lower()
        vector = np.zeros(self._dimension, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9_]+", text)
        if not tokens:
            tokens = [text]

        for token in tokens:
            token_hash = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            vector[token_hash % self._dimension] += 1.0

        compact = text.replace(" ", "")
        for index in range(max(0, len(compact) - 2)):
            trigram = compact[index : index + 3]
            trigram_hash = int(hashlib.md5(trigram.encode("utf-8")).hexdigest(), 16)
            vector[trigram_hash % self._dimension] += 0.35

        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector


class JsonVectorDataManager(DataManager):
    """JSON-file vector store that persists prompt digests, never prompt text."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._entries, migrated = _read_entries(self.storage_path)
        if migrated:
            # Rewrite entries written by earlier versions so their raw prompt
            # text does not stay on disk.
            self.flush()

    def save(self, question: Any, answer: Any, embedding_data: Any, **kwargs: Any) -> None:
        del kwargs
        self.import_data(
            questions=[question],
            answers=[answer],
            embedding_datas=[embedding_data],
            session_ids=[None],
        )

    def import_data(
        self,
        questions: list[Any],
        answers: list[Any],
        embedding_datas: list[Any],
        session_ids: list[str | None],
    ) -> None:
        del session_ids
        with self._lock:
            next_id = 1 + max((entry["id"] for entry in self._entries), default=0)
            for question, answer, embedding in zip(
                questions,
                answers,
                embedding_datas,
                strict=True,
            ):
                self._entries.append(
                    {
                        "id": next_id,
                        QUESTION_DIGEST_FIELD: prompt_digest(str(question)),
                        "answer": str(answer),
                        "embedding": np.asarray(embedding, dtype=np.float32).tolist(),
                    }
                )
                next_id += 1
            self.flush()

    def get_scalar_data(self, res_data: Any, **kwargs: Any) -> CacheData | None:
        del kwargs
        _, entry_id = res_data
        for entry in self._entries:
            if entry["id"] == entry_id:
                return CacheData(
                    question=entry[QUESTION_DIGEST_FIELD],
                    answers=entry["answer"],
                    embedding_data=np.asarray(entry["embedding"], dtype=np.float32),
                )
        return None

    def search(self, embedding_data: Any, **kwargs: Any) -> list[tuple[float, int]]:
        query = np.asarray(embedding_data, dtype=np.float32)
        top_k = kwargs.get("top_k", -1)
        scored = [
            (
                float(np.linalg.norm(query - np.asarray(entry["embedding"], dtype=np.float32))),
                int(entry["id"]),
            )
            for entry in self._entries
        ]
        scored.sort(key=lambda item: item[0])
        if top_k is None or top_k < 0:
            return scored
        return scored[:top_k]

    def add_session(self, res_data: Any, session_id: str, pre_embedding_data: Any) -> None:
        del res_data, session_id, pre_embedding_data

    def list_sessions(self, session_id: str | None, key: Any) -> list[Any]:
        del session_id, key
        return []

    def delete_session(self, session_id: str) -> None:
        del session_id

    def close(self) -> None:
        self.flush()

    def flush(self) -> None:
        with self._lock:
            _write_entries(self.storage_path, self._entries)


class ExactPromptEvaluation(SearchDistanceEvaluation):
    """Similarity evaluation that only accepts entries stored for the same prompt.

    A single word can invert the meaning of a rule ("5 or higher" versus
    "5 or lower"), so embedding distance alone must never select another prompt's
    translation. Entries whose digest differs from the query's digest get a rank
    below GPTCache's minimum, which no similarity threshold can accept.
    """

    def evaluation(
        self, src_dict: dict[str, Any], cache_dict: dict[str, Any], **kwargs: Any
    ) -> float:
        cached_question = cache_dict.get("question")
        query_question = src_dict.get("question")
        if (
            not isinstance(cached_question, str)
            or not isinstance(query_question, str)
            or cached_question != prompt_digest(query_question)
        ):
            return -1.0
        return float(super().evaluation(src_dict, cache_dict, **kwargs))


class GPTSemanticTranslationCache:
    def __init__(
        self,
        *,
        root_dir: Path,
        similarity_threshold: float,
        embedding_dimension: int = 256,
    ) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        migrate_cache_files(self.root_dir)
        self.similarity_threshold = similarity_threshold
        self.embedding_dimension = embedding_dimension
        self._embedding = HashingEmbedding(dimension=embedding_dimension)
        self._caches: dict[str, Cache] = {}

    def get(self, *, scope_key: str, prompt_text: str) -> SemanticCacheHit | None:
        cache = self._get_cache(scope_key)
        similarity: float | None = None

        def hit_callback(matches: list[tuple[str, float]]) -> None:
            nonlocal similarity
            if matches:
                similarity = max(score for _, score in matches)

        cached = gptcache_get(prompt_text, cache_obj=cache, hit_callback=hit_callback)
        if cached is None:
            return None
        return SemanticCacheHit(
            response_text=str(cached),
            cache=CacheInsight(
                backend="gptcache",
                enabled=True,
                hit=True,
                scope_key=scope_key,
                similarity=similarity,
            ),
        )

    def put(self, *, scope_key: str, prompt_text: str, response_text: str) -> CacheInsight:
        cache = self._get_cache(scope_key)
        gptcache_put(prompt_text, response_text, cache_obj=cache)
        cache.flush()
        return CacheInsight(
            backend="gptcache",
            enabled=True,
            hit=False,
            scope_key=scope_key,
        )

    def _get_cache(self, scope_key: str) -> Cache:
        if scope_key not in self._caches:
            cache = Cache()
            cache.init(
                pre_embedding_func=get_prompt,
                embedding_func=self._embedding.to_embeddings,
                data_manager=JsonVectorDataManager(self._storage_path(scope_key)),
                similarity_evaluation=ExactPromptEvaluation(max_distance=2.0),
                config=Config(
                    similarity_threshold=self.similarity_threshold,
                    enable_token_counter=False,
                ),
            )
            self._caches[scope_key] = cache
        return self._caches[scope_key]

    def _storage_path(self, scope_key: str) -> Path:
        digest = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()
        return self.root_dir / f"{digest}.json"
