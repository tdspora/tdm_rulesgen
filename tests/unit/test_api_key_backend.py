from __future__ import annotations

import asyncio

import pytest

from rulesgen.auth.backends import api_key as api_key_module
from rulesgen.auth.backends.api_key import ApiKeyBackend, is_usable_api_key
from rulesgen.auth.models import AuthContext, Principal


def _authenticate(configured_key: str, provided_key: str | None) -> Principal | None:
    backend = ApiKeyBackend(configured_key)
    return asyncio.run(backend.authenticate(AuthContext(api_key=provided_key)))


def test_matching_key_is_authenticated() -> None:
    principal = _authenticate("s3cret-key", "s3cret-key")

    assert principal is not None
    assert principal.auth_type == "api_key"
    assert principal.subject == "api-key-client"


@pytest.mark.parametrize("provided_key", [None, "", "wrong-key", "s3cret-ke", "s3cret-key "])
def test_other_keys_are_rejected(provided_key: str | None) -> None:
    assert _authenticate("s3cret-key", provided_key) is None


@pytest.mark.parametrize("configured_key", ["change-me", ""])
@pytest.mark.parametrize("provided_key", [None, "", "change-me"])
def test_placeholder_or_empty_configured_key_accepts_nothing(
    configured_key: str, provided_key: str | None
) -> None:
    assert _authenticate(configured_key, provided_key) is None


@pytest.mark.parametrize(
    ("api_key", "usable"),
    [("change-me", False), ("", False), ("Change-Me", True), ("s3cret-key", True)],
)
def test_is_usable_api_key(api_key: str, usable: bool) -> None:
    assert is_usable_api_key(api_key) is usable


def test_keys_are_compared_in_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    compared: list[tuple[bytes, bytes]] = []

    def recording_compare_digest(left: bytes, right: bytes) -> bool:
        compared.append((left, right))
        return left == right

    monkeypatch.setattr(api_key_module.hmac, "compare_digest", recording_compare_digest)

    assert _authenticate("s3cret-key", "wrong-key") is None
    assert _authenticate("s3cret-key", "s3cret-key") is not None
    assert compared == [(b"wrong-key", b"s3cret-key"), (b"s3cret-key", b"s3cret-key")]


def test_keys_with_undecodable_environment_bytes_still_compare() -> None:
    # os.environ decodes invalid UTF-8 with surrogateescape.
    configured_key = b"s3cret-\xff".decode("utf-8", "surrogateescape")

    assert _authenticate(configured_key, configured_key) is not None
    assert _authenticate(configured_key, "s3cret-") is None
