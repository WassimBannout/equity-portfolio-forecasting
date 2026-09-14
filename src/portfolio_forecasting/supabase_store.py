"""Bounded Supabase database-function transport and coherent read/write contracts."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from portfolio_forecasting.publication import PublicationSettings
from portfolio_forecasting.snapshots import (
    canonical_bytes,
    digest,
    read_snapshot,
    write_content,
)
from portfolio_forecasting.store_contract import (
    StoreConflict,
    StoreError,
    hash_value,
    iso_date,
    iso_time,
    object_value,
    validate_published_run,
)

MAX_BYTES = 16 * 1024 * 1024
Transport = Callable[[str, bytes, dict[str, str], float], bytes]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise StoreError("storage redirects are refused")


def http_transport(
    url: str, body: bytes, headers: dict[str, str], timeout: float
) -> bytes:
    request = Request(url, data=body, headers=headers, method="POST")
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        data: bytes = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise StoreError("storage response exceeds the bounded size")
    return data


@dataclass(frozen=True, slots=True)
class StoreCredentials:
    settings: PublicationSettings
    access_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.access_token is not None and (
            not isinstance(self.access_token, str)
            or not self.access_token
            or any(character.isspace() for character in self.access_token)
        ):
            raise StoreError("invalid SUPABASE_ACCESS_TOKEN")
        if self.settings.key.startswith("sb_secret_"):
            raise StoreError("use a publishable key and a restricted writer token")

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> StoreCredentials:
        source = os.environ if environment is None else environment
        return cls(
            PublicationSettings.from_environment(source),
            source.get("SUPABASE_ACCESS_TOKEN"),
        )


class SupabaseStore:
    def __init__(
        self,
        credentials: StoreCredentials,
        *,
        transport: Transport = http_transport,
        sleeper: Callable[[float], None] = time.sleep,
        api_prefix: str = "/rest/v1",
    ) -> None:
        if api_prefix not in ("/rest/v1", ""):
            raise StoreError("invalid database API prefix")
        self.credentials = credentials
        self._transport = transport
        self._sleep = sleeper
        # Empty prefix is only for a disposable native PostgREST verification.
        self._base = credentials.settings.url.rstrip("/") + api_prefix

    def rpc(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if not re.fullmatch(r"pf_[a-z_]+", name):
            raise StoreError("unsupported database function name")
        try:
            body = canonical_bytes(arguments)
        except (ValueError, TypeError, OverflowError) as error:
            raise StoreError("invalid storage serialization") from error
        if len(body) > MAX_BYTES:
            raise StoreError("storage request exceeds the bounded size")
        headers = {
            "apikey": self.credentials.settings.key,
            "Content-Type": "application/json",
        }
        token = self.credentials.access_token
        if token is None and self.credentials.settings.key.startswith("eyJ"):
            token = self.credentials.settings.key
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        for attempt in range(1, 4):
            try:
                raw = self._transport(self._base + "/rpc/" + name, body, headers, 15.0)
                if len(raw) > MAX_BYTES:
                    raise StoreError("storage response exceeds the bounded size")
                return json.loads(raw, parse_constant=lambda value: _invalid_json())
            except HTTPError as error:
                status = error.code
                error.close()
                if status == 409:
                    raise StoreConflict(
                        "immutable publication content conflicts"
                    ) from None
                if status not in (429, 500, 502, 503, 504):
                    raise StoreError(
                        f"Supabase rejected request (HTTP {status})"
                    ) from None
            except (URLError, TimeoutError, ConnectionError, OSError):
                pass
            except (json.JSONDecodeError, UnicodeError):
                raise StoreError("malformed storage JSON response") from None
            if attempt == 3:
                raise StoreError(
                    "Supabase request failed after 3 bounded attempts"
                ) from None
            logging.getLogger(__name__).warning(
                "stage=storage function=%s attempt=%d status=retry",
                name,
                attempt,
            )
            self._sleep(float(2 ** (attempt - 1)))
        raise AssertionError("unreachable retry state")

    def preflight(self, *, writer: bool = False) -> None:
        access = object_value(self.rpc("pf_access", {}), "database access")
        allowed = (
            ("portfolio_writer",)
            if writer
            else ("anon", "authenticated", "portfolio_writer")
        )
        if access.get("schema_version") != 1 or access.get("role") not in allowed:
            raise StoreError("database role or schema does not permit this operation")

    def lookup(
        self, *, identity: dict[str, Any] | None = None, run_id: str | None = None
    ) -> dict[str, Any] | None:
        if (identity is None) == (run_id is None):
            raise StoreError("lookup needs exactly one identity or run ID")
        if run_id is not None:
            UUID(run_id)
        result = self.rpc("pf_lookup", {"p_identity": identity, "p_run_id": run_id})
        if result is None:
            return None
        row = object_value(result, "bound run")
        try:
            UUID(row["run_id"])
            hash_value(row["request_key"])
            hash_value(row["snapshot_sha256"])
            if row["state"] not in ("staged", "published"):
                raise StoreError("invalid stored run state")
            if identity is not None and row["identity"] != identity:
                raise StoreError("lookup returned a different scientific request")
            if run_id is not None and row["run_id"] != run_id:
                raise StoreError("lookup returned a different run")
        except (KeyError, TypeError, ValueError) as error:
            raise StoreError("malformed bound-run response") from error
        return row

    def stage(
        self,
        identity: dict[str, Any],
        snapshot: Path,
        attempt_id: str,
        started_at: datetime,
    ) -> dict[str, Any]:
        read_snapshot(snapshot)
        self.rpc(
            "pf_stage",
            {
                "p_identity": identity,
                "p_snapshot": snapshot.read_bytes().decode(),
                "p_attempt_id": str(UUID(attempt_id)),
                "p_started_at": started_at,
            },
        )
        row = self.lookup(identity=identity)
        if row is None or row["snapshot_sha256"] != snapshot.stem:
            raise StoreError("snapshot binding read-back failed")
        return row

    def bound_snapshot(self, snapshot_hash: str, directory: Path) -> Path:
        hash_value(snapshot_hash)
        record = object_value(
            self.rpc("pf_snapshot", {"p_hash": snapshot_hash}), "snapshot"
        )
        try:
            raw = record["content"].encode("utf-8")
            if (
                record["snapshot_sha256"] != snapshot_hash
                or digest(raw) != snapshot_hash
            ):
                raise StoreError("durable snapshot hash mismatch")
            path = write_content(raw, directory)
            read_snapshot(path)
            return path
        except (KeyError, TypeError, AttributeError) as error:
            raise StoreError("malformed durable snapshot") from error

    def attempt(self, run_id: str, attempt_id: str, started_at: datetime) -> None:
        self.rpc(
            "pf_attempt",
            {
                "p_run_id": str(UUID(run_id)),
                "p_attempt_id": str(UUID(attempt_id)),
                "p_started_at": started_at,
            },
        )

    def publish(
        self,
        run_id: str,
        payload: dict[str, Any],
        attempt_id: str,
        completed_at: datetime,
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        self.rpc(
            "pf_publish",
            {
                "p_run_id": str(UUID(run_id)),
                "p_payload": payload,
                "p_attempt_id": str(UUID(attempt_id)),
                "p_completed_at": completed_at,
                "p_diagnostics": diagnostics,
            },
        )
        run = self.get_run(run_id)
        if run["scientific_payload"] != payload:
            raise StoreError(
                "published scientific read-back differs from submitted content"
            )
        return run

    def fail(self, run_id: str, attempt_id: str, stage: str) -> None:
        self.rpc(
            "pf_fail",
            {"p_run_id": run_id, "p_attempt_id": attempt_id, "p_stage": stage},
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = validate_published_run(
            self.rpc("pf_run", {"p_run_id": str(UUID(run_id))})
        )
        if run["run_id"] != run_id:
            raise StoreError("complete-run response contains a different identity")
        return run

    def runs(
        self,
        *,
        limit: int = 50,
        cursor: dict[str, Any] | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        return self._page("pf_runs", limit, cursor, as_of, {})

    def history(
        self,
        ticker: str,
        start: date,
        end: date,
        *,
        limit: int = 50,
        cursor: dict[str, Any] | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        return self._page(
            "pf_history",
            limit,
            cursor,
            as_of,
            {"p_ticker": ticker, "p_start": start, "p_end": end},
        )

    def _page(
        self,
        function: str,
        limit: int,
        cursor: dict[str, Any] | None,
        as_of: str | None,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise StoreError("page limit must be between 1 and 100")
        page = object_value(
            self.rpc(
                function,
                {
                    "p_limit": limit,
                    "p_cursor": cursor,
                    "p_as_of": as_of,
                    **extra,
                },
            ),
            "page",
        )
        try:
            iso_time(page["as_of"])
            items = page["items"]
            if not isinstance(items, list) or len(items) > limit:
                raise StoreError("invalid bounded page")
            ids = []
            for item in items:
                ids.append(str(UUID(item["run_id"])))
                iso_date(item["target"])
                iso_time(item["published_at"])
            if len(set(ids)) != len(ids) or (
                page["next_cursor"] is not None
                and (not items or page["next_cursor"] == cursor)
            ):
                raise StoreError("duplicate or non-progressing page")
        except (KeyError, TypeError, ValueError) as error:
            raise StoreError("malformed historical page") from error
        return page

    def observe(self, run_id: str, snapshot: Path) -> dict[str, Any]:
        read_snapshot(snapshot)
        return object_value(
            self.rpc(
                "pf_observe",
                {
                    "p_run_id": str(UUID(run_id)),
                    "p_snapshot": snapshot.read_bytes().decode(),
                },
            ),
            "outcome association",
        )


def _invalid_json() -> None:
    raise StoreError("nonfinite storage JSON value")
