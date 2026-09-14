import copy
import io
import json
from dataclasses import replace
from datetime import timedelta
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

import pytest

from portfolio_forecasting.allocation import allocate_forecasts
from portfolio_forecasting.forecasting import FIT_OPTIONS, AssetForecast, model_options
from portfolio_forecasting.market_data import PreparedData
from portfolio_forecasting.pipeline import ForecastReport
from portfolio_forecasting.portfolio import PortfolioReport
from portfolio_forecasting.publication import PublicationSettings
from portfolio_forecasting.snapshots import canonical_bytes, write_snapshot
from portfolio_forecasting.store_contract import (
    Release,
    StoreConflict,
    StoreError,
    identity_for,
    publication_payload,
    validate_published_run,
)
from portfolio_forecasting.supabase_store import (
    StoreCredentials,
    SupabaseStore,
    _NoRedirect,
)


@pytest.fixture
def report(prepared: PreparedData, tmp_path: Path) -> PortfolioReport:
    forecasts = tuple(
        AssetForecast(
            asset.ticker,
            prepared.plan.observation_cutoff,
            prepared.plan.forecast_target,
            asset.observations[-1].price,
            asset.observations[-1].price * 1.001,
            0.001,
            canonical_bytes(
                {"constructor": model_options(prepared), "fit": FIT_OPTIONS}
            ).decode(),
        )
        for asset in prepared.assets
    )
    now = prepared.resolved.executed_at
    return PortfolioReport(
        ForecastReport(
            str(uuid4()),
            prepared,
            forecasts,
            write_snapshot(prepared, tmp_path),
            now,
            (),
        ),
        allocate_forecasts(prepared, forecasts),
        now,
        0.0,
    )


@pytest.fixture
def release() -> Release:
    return Release.capture(Path("uv.lock"))


def reader_record(report: PortfolioReport, release: Release) -> dict[str, Any]:
    payload = publication_payload(report, release)
    snapshot = json.loads(report.forecast.snapshot_path.read_text())
    return {
        "run_id": str(uuid4()),
        "request_key": "a" * 64,
        "snapshot_sha256": report.forecast.snapshot_path.stem,
        "result_sha256": "b" * 64,
        "state": "published",
        "identity": identity_for(
            report.forecast.data.resolved, report.forecast.data.plan, release
        ),
        "executed_at": report.completed_at.isoformat(),
        "published_at": report.completed_at.isoformat(),
        "completed_at": report.completed_at.isoformat(),
        "target_open": report.forecast.data.plan.target_open.isoformat(),
        "target_close": report.forecast.data.plan.target_close.isoformat(),
        "input_provenance": {
            "data_sha256": snapshot["data_sha256"],
            "price_basis": snapshot["price_basis"],
            "provider_options": snapshot["provider_options"],
            "assets": [
                {key: value for key, value in item.items() if key != "observations"}
                for item in sorted(snapshot["assets"], key=lambda item: item["ticker"])
            ],
        },
        "scientific_payload": payload,
        "assets": [
            {**asset, "outcome": None} for asset in copy.deepcopy(payload["assets"])
        ],
    }


def credentials() -> StoreCredentials:
    return StoreCredentials(
        PublicationSettings(url="https://example.supabase.co", key="test-api-key"),
        "server-token-secret",
    )


def test_identity_ignores_attempt_time_and_ticker_order(
    prepared: PreparedData, release: Release
) -> None:
    identity = identity_for(prepared.resolved, prepared.plan, release)
    changed = replace(
        prepared.resolved,
        executed_at=prepared.resolved.executed_at + timedelta(minutes=1),
        request=replace(
            prepared.resolved.request,
            tickers=tuple(reversed(prepared.resolved.request.tickers)),
        ),
    )
    assert identity_for(changed, prepared.plan, release) == identity
    revision = replace(
        changed, request=replace(changed.request, scientific_revision="2")
    )
    assert identity_for(revision, prepared.plan, release) != identity
    other = Release("c" * 64, release.software_json)
    assert identity_for(prepared.resolved, prepared.plan, other) != identity


def test_payload_preserves_numbers_dates_and_rejects_missing_membership(
    report: PortfolioReport, release: Release
) -> None:
    payload = publication_payload(report, release)
    assert len(payload["assets"]) == 2
    assert payload["assets"][0]["recent_history"][-1]["session"] == "2026-09-04"
    assert payload["risk_estimator"] == "observed_sample_ddof1"
    with pytest.raises(StoreError):
        publication_payload(
            replace(
                report,
                forecast=replace(
                    report.forecast, forecasts=report.forecast.forecasts[:1]
                ),
            ),
            release,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None, True])
def test_invalid_weights_fail_before_persistence(
    report: PortfolioReport, release: Release, bad: Any
) -> None:
    with pytest.raises(ValueError):
        publication_payload(
            replace(report, allocation=replace(report.allocation, weights=(bad, 0.5))),
            release,
        )


def test_changed_covariance_and_price_basis_rejected(
    report: PortfolioReport, release: Release
) -> None:
    with pytest.raises(StoreError, match="risk"):
        publication_payload(
            replace(
                report,
                allocation=replace(
                    report.allocation, covariance=((1.0, 0.0), (0.0, 1.0))
                ),
            ),
            release,
        )
    item = replace(report.forecast.forecasts[0], observed_price=1.0)
    with pytest.raises(StoreError, match="basis"):
        publication_payload(
            replace(
                report,
                forecast=replace(
                    report.forecast, forecasts=(item, report.forecast.forecasts[1])
                ),
            ),
            release,
        )


def test_complete_read_detects_truncation_and_mixing(
    report: PortfolioReport, release: Release
) -> None:
    original = reader_record(report, release)
    assert validate_published_run(original) == original
    partial = copy.deepcopy(original)
    partial["assets"].pop()
    with pytest.raises(StoreError, match="membership"):
        validate_published_run(partial)
    changed = copy.deepcopy(original)
    changed["assets"][0]["recent_history"].pop(0)
    with pytest.raises(StoreError, match="immutable scientific"):
        validate_published_run(changed)
    invalid = copy.deepcopy(original)
    invalid["assets"][0]["weight"] = None
    with pytest.raises(StoreError):
        validate_published_run(invalid)


def test_target_mismatch_and_nonfinite_nested_results_rejected(
    report: PortfolioReport, release: Release
) -> None:
    value = reader_record(report, release)
    value["assets"][0]["outcome"] = {
        "target": "2026-09-09",
        "state": "matched",
        "actual_price": 100.0,
    }
    with pytest.raises(StoreError, match="target"):
        validate_published_run(value)
    value = reader_record(report, release)
    value["scientific_payload"]["solver"]["bad"] = float("inf")
    with pytest.raises(StoreError):
        validate_published_run(value)


def test_rpc_retries_same_body_with_bounded_delays_and_timeout() -> None:
    calls = []
    sleeps: list[float] = []

    def transport(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> bytes:
        calls.append((url, body, headers, timeout))
        if len(calls) < 3:
            raise HTTPError(
                url,
                503,
                "secret response",
                Message(),
                io.BytesIO(b"server-token-secret"),
            )
        return b'{"ok":true}'

    store = SupabaseStore(credentials(), transport=transport, sleeper=sleeps.append)
    assert store.rpc("pf_publish", {"p_value": 1}) == {"ok": True}
    assert len(calls) == 3 and sleeps == [1.0, 2.0]
    assert len({call[1] for call in calls}) == 1
    assert all(call[3] == 15.0 for call in calls)
    assert calls[0][2]["Authorization"] == "Bearer server-token-secret"


@pytest.mark.parametrize("status", [400, 401, 403, 409, 410])
def test_permanent_http_errors_are_not_retried_or_leaked(status: int) -> None:
    calls = []

    def transport(
        url: str, body: bytes, headers: dict[str, str], timeout: float
    ) -> bytes:
        calls.append(url)
        raise HTTPError(
            url,
            status,
            "server-token-secret",
            Message(),
            io.BytesIO(b"server-token-secret"),
        )

    with pytest.raises(StoreConflict if status == 409 else StoreError) as error:
        SupabaseStore(credentials(), transport=transport).rpc("pf_stage", {})
    assert len(calls) == 1 and "server-token-secret" not in str(error.value)


def test_transport_exhaustion_and_malformed_json() -> None:
    count = 0

    def broken(url: str, body: bytes, headers: dict[str, str], timeout: float) -> bytes:
        nonlocal count
        count += 1
        raise TimeoutError("server-token-secret")

    with pytest.raises(StoreError, match="3 bounded"):
        SupabaseStore(credentials(), transport=broken, sleeper=lambda value: None).rpc(
            "pf_run", {}
        )
    assert count == 3
    for body in (b"not-json", b'{"bad":NaN}'):
        with pytest.raises(StoreError):
            SupabaseStore(credentials(), transport=lambda *args, body=body: body).rpc(
                "pf_run", {}
            )


def test_no_redirect_and_no_secret_in_repr() -> None:
    value = credentials()
    assert value.access_token is not None
    assert value.settings.key not in repr(value)
    assert value.access_token not in repr(value)
    with pytest.raises(StoreError, match="redirect"):
        _NoRedirect().redirect_request(
            Request("https://example.supabase.co"),
            None,
            302,
            "",
            {},
            "https://elsewhere.example",
        )
    with pytest.raises(StoreError):
        StoreCredentials(
            PublicationSettings(
                url="https://example.supabase.co", key="sb_secret_disallowed"
            )
        )


def test_role_preflight_and_bad_page_response() -> None:
    store = SupabaseStore(
        credentials(), transport=lambda *args: b'{"role":"anon","schema_version":1}'
    )
    store.preflight()
    with pytest.raises(StoreError):
        store.preflight(writer=True)
    with pytest.raises(StoreError):
        store.runs(limit=101)
    page = {
        "items": [],
        "as_of": "2026-09-08T09:00:00+00:00",
        "next_cursor": {"run_id": "missing"},
    }
    store = SupabaseStore(
        credentials(), transport=lambda *args: json.dumps(page).encode()
    )
    with pytest.raises(StoreError):
        store.runs()
