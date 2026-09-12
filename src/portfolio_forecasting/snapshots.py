"""Canonical, content-addressed local input snapshots and verified offline reads."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from importlib.metadata import distributions
from importlib.resources import files
from pathlib import Path
from typing import Any

from portfolio_forecasting.config import (
    AllocationSettings,
    DataSettings,
    ForecastSettings,
    RunRequest,
)
from portfolio_forecasting.errors import ForecastError
from portfolio_forecasting.market_data import (
    AssetHistory,
    Observation,
    PreparedData,
    history_options,
    prepare_data,
)
from portfolio_forecasting.sessions import plan_sessions


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"unsupported metadata type: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        default=_json_default,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def software_metadata() -> dict[str, object]:
    root = files("portfolio_forecasting")
    sources = {
        item.name: digest(item.read_bytes())
        for item in root.iterdir()
        if item.name.endswith(".py")
    }
    installed = {
        dist.metadata["Name"].lower().replace("_", "-"): dist.version
        for dist in distributions()
    }
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": dict(sorted(installed.items())),
        "source_sha256": digest(canonical_bytes(sources)),
        "source_files": sources,
    }


def input_payload(data: PreparedData) -> dict[str, object]:
    observations = [
        {
            "ticker": asset.ticker,
            "provider": asset.provider,
            "metadata": dict(asset.metadata),
            "observations": asset.observations,
        }
        for asset in data.assets
    ]
    return {
        "schema_version": 1,
        "kind": "forecast_inputs",
        "request": data.resolved.to_metadata(),
        "plan": data.plan,
        "assets": data.assets,
        "price_basis": "adjusted_close",
        "provider_options": history_options(data.resolved),
        "data_sha256": digest(canonical_bytes(observations)),
        "software": software_metadata(),
    }


def write_snapshot(data: PreparedData, directory: Path) -> Path:
    content = canonical_bytes(input_payload(data))
    return write_content(content, directory)


def write_content(content: bytes, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest(content)}.json"
    # Publish only a complete file. Hard-link creation cannot overwrite an existing
    # snapshot, including when another process captures the same content.
    with tempfile.NamedTemporaryFile(
        dir=directory, prefix=".snapshot-", delete=False
    ) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.chmod(temporary, 0o444)
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != content:
                    raise ForecastError(
                        "snapshot", "existing snapshot content does not match its hash"
                    ) from None
        finally:
            temporary.unlink(missing_ok=True)
    return target


def read_snapshot(path: Path, *, require_same_software: bool = False) -> PreparedData:
    try:
        content = path.read_bytes()
        if path.name != f"{digest(content)}.json":
            raise ForecastError("snapshot", "snapshot hash mismatch")
        payload: dict[str, Any] = json.loads(content)
        if payload["schema_version"] != 1 or payload["kind"] != "forecast_inputs":
            raise ForecastError("snapshot", "unsupported input snapshot schema")
        if require_same_software:
            current = software_metadata()
            captured = payload["software"]
            runtime_names = (
                "prophet",
                "cmdstanpy",
                "numpy",
                "pandas",
                "exchange-calendars",
                "yfinance",
                "tzdata",
                "holidays",
            )
            current_packages = (
                dict(current["packages"])
                if isinstance(current["packages"], dict)
                else {}
            )
            if (
                captured["source_sha256"] != current["source_sha256"]
                or captured["python"] != current["python"]
                or any(
                    captured["packages"].get(name) != current_packages.get(name)
                    for name in runtime_names
                )
            ):
                raise ForecastError(
                    "snapshot",
                    "replay requires the captured source "
                    "and scientific dependency versions",
                )
        meta = payload["request"]
        request = RunRequest(
            tickers=meta["tickers"],
            history_start=date.fromisoformat(meta["history_start"]),
            history_end=date.fromisoformat(meta["requested_history_end"])
            if meta["requested_history_end"]
            else None,
            mode=meta["mode"],
            scientific_revision=meta["scientific_revision"],
            forecast=ForecastSettings(**meta["forecast"]),
            allocation=AllocationSettings(**meta["allocation"]),
            data=DataSettings(**meta["data"]),
        )
        resolved = request.resolve(
            clock=lambda: datetime.fromisoformat(meta["executed_at"])
        )
        plan = plan_sessions(resolved)
        if plan is None or canonical_bytes(plan) != canonical_bytes(payload["plan"]):
            raise ForecastError(
                "snapshot", "captured calendar differs from the installed calendar"
            )
        assets = tuple(
            AssetHistory(
                ticker=asset["ticker"],
                observations=tuple(
                    Observation(date.fromisoformat(row["session"]), row["price"])
                    for row in asset["observations"]
                ),
                metadata=tuple(tuple(pair) for pair in asset["metadata"]),
                retrieved_at=datetime.fromisoformat(asset["retrieved_at"]),
                attempts=asset["attempts"],
                provider=asset["provider"],
            )
            for asset in payload["assets"]
        )
        data = prepare_data(resolved, plan, assets)
        reconstructed = input_payload(data)
        for key in ("request", "provider_options", "price_basis", "data_sha256"):
            if canonical_bytes(reconstructed[key]) != canonical_bytes(payload[key]):
                raise ForecastError("snapshot", f"inconsistent snapshot {key}")
        return data
    except ForecastError:
        raise
    except (OSError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise ForecastError(
            "snapshot", "unreadable or malformed input snapshot"
        ) from error
