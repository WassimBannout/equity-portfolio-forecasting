"""Credential boundary validation, with no real credentials or service access."""

from pathlib import Path
from typing import Any

import pytest

from portfolio_forecasting import PublicationSettings


@pytest.mark.parametrize(
    "environment,missing",
    [
        ({}, "SUPABASE_URL, SUPABASE_KEY"),
        ({"SUPABASE_URL": "https://example.supabase.co"}, "SUPABASE_KEY"),
        ({"SUPABASE_KEY": "test-token"}, "SUPABASE_URL"),
        ({"SUPABASE_URL": "", "SUPABASE_KEY": ""}, "SUPABASE_URL, SUPABASE_KEY"),
    ],
)
def test_missing_publication_settings(
    environment: dict[str, str], missing: str
) -> None:
    with pytest.raises(ValueError, match=missing):
        PublicationSettings.from_environment(environment)


def test_explicit_mapping_does_not_fall_back_to_process_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "dummy-private-test-value")
    with pytest.raises(ValueError, match="missing publication settings"):
        PublicationSettings.from_environment({})
    settings = PublicationSettings.from_environment()
    assert settings.key == "dummy-private-test-value"
    assert settings.key not in repr(settings)


def test_no_implicit_dotenv_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "SUPABASE_URL=https://example.supabase.co\nSUPABASE_KEY=dummy-token\n"
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="missing publication settings"):
        PublicationSettings.from_environment()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.supabase.co",
        "https://example.supabase.co/",
        "http://localhost:54321",
        "http://127.0.0.1:54321",
        "http://[::1]:54321",
    ],
)
def test_valid_production_or_loopback_base_url(url: str) -> None:
    settings = PublicationSettings(url=url, key="dummy-token")
    assert settings.url == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "http://example.com",
        "https://",
        "https://example.com:bad",
        "https://example.com:0",
        "https://example.com:65536",
        "https://[::1",
        "https://example.com/rest/v1",
        "https://example.com?token=do-not-print",
        "https://user:do-not-print@example.com",
        "https://example.com#fragment",
        "https://exam ple.com",
        "ftp://example.com",
    ],
)
def test_invalid_endpoints_do_not_echo_sensitive_input(url: str) -> None:
    with pytest.raises(ValueError, match="SUPABASE_URL") as error:
        PublicationSettings(url=url, key="do-not-print")
    assert "do-not-print" not in str(error.value)


@pytest.mark.parametrize("key", ["", " ", "dummy token", "dummy\nvalue", None, 123])
def test_invalid_credentials(key: Any) -> None:
    with pytest.raises(ValueError, match="SUPABASE_KEY"):
        PublicationSettings(url="https://example.supabase.co", key=key)
