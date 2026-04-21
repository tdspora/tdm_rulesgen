from __future__ import annotations

from rulesgen.core.config import Settings


def test_settings_parses_csv_list_fields_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "RULESGEN_CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://localhost:8000",
    )
    monkeypatch.setenv(
        "RULESGEN_TRUSTED_HOSTS",
        "localhost,127.0.0.1,testserver,rulesgen",
    )

    settings = Settings()

    assert settings.cors_allow_origins == [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    assert settings.trusted_hosts == [
        "localhost",
        "127.0.0.1",
        "testserver",
        "rulesgen",
    ]


def test_settings_parses_json_list_fields_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "RULESGEN_CORS_ALLOW_ORIGINS",
        '["http://localhost:3000", "http://localhost:8000"]',
    )
    monkeypatch.setenv(
        "RULESGEN_TRUSTED_HOSTS",
        '["localhost", "127.0.0.1", "testserver", "rulesgen"]',
    )

    settings = Settings()

    assert settings.cors_allow_origins == [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    assert settings.trusted_hosts == [
        "localhost",
        "127.0.0.1",
        "testserver",
        "rulesgen",
    ]
