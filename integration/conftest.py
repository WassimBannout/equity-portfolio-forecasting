import base64
import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from portfolio_forecasting.config import (
    AllocationSettings,
    ForecastSettings,
    RunRequest,
)
from portfolio_forecasting.market_data import PreparedData, prepare_data, utc_now
from portfolio_forecasting.publication import PublicationSettings
from portfolio_forecasting.sessions import plan_sessions
from portfolio_forecasting.supabase_store import StoreCredentials, SupabaseStore

POSTGREST_URL = "https://github.com/PostgREST/postgrest/releases/download/v16.3/postgrest-v16.3-linux-static-x86-64.tar.xz"
POSTGREST_SHA256 = "4eb414eb948c8800863cc8c9896a17b611b2dccf9ff581f4d57f42ec9ccee40d"
ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Database:
    root: Path
    url: str
    environment: dict[str, str] = field(repr=False)
    secret: str = field(repr=False)

    def token(self, role: str) -> str:
        def encode(value: bytes) -> str:
            return base64.urlsafe_b64encode(value).decode().rstrip("=")

        header = encode(b'{"alg":"HS256","typ":"JWT"}')
        body = encode(
            json.dumps({"role": role, "exp": int(time.time()) + 3600}).encode()
        )
        message = header + "." + body
        signature = hmac.new(
            self.secret.encode(), message.encode(), hashlib.sha256
        ).digest()
        return message + "." + encode(signature)

    def client(self, role: str = "portfolio_writer") -> SupabaseStore:
        return SupabaseStore(
            StoreCredentials(
                PublicationSettings(url=self.url, key="disposable-api-key"),
                self.token(role),
            ),
            api_prefix="",
            sleeper=lambda duration: None,
        )

    def sql(self, statement: str, *, ok: bool = True) -> str:
        result = subprocess.run(
            ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1"],
            input=statement,
            env=self.environment,
            text=True,
            capture_output=True,
        )
        if ok and result.returncode:
            raise AssertionError(result.stderr)
        if not ok and result.returncode == 0:
            raise AssertionError("SQL unexpectedly succeeded")
        return result.stdout if ok else result.stderr


@pytest.fixture(scope="session")
def database() -> Iterator[Database]:
    pg = Path(os.environ.get("M4_POSTGRES_BIN", "/usr/lib/postgresql/16/bin"))
    if not (pg / "initdb").is_file():
        pytest.fail("real database gate requires PostgreSQL server binaries")
    tools = ROOT / "artifacts/milestone4/tools"
    tools.mkdir(parents=True, exist_ok=True)
    archive = tools / "postgrest-v16.3-linux-static-x86-64.tar.xz"
    if not archive.exists():
        with urllib.request.urlopen(POSTGREST_URL, timeout=60) as response:
            archive.write_bytes(response.read())
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == POSTGREST_SHA256
    with tarfile.open(archive) as bundle:
        bundle.extractall(tools, filter="data")
    with TemporaryDirectory(prefix="portfolio-m4-integration-") as temporary:
        root = Path(temporary)
        subprocess.run(
            [
                str(pg / "initdb"),
                "-D",
                str(root / "data"),
                "-U",
                "pf_admin",
                "-A",
                "trust",
                "--no-locale",
                "--encoding=UTF8",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(pg / "pg_ctl"),
                "-D",
                str(root / "data"),
                "-l",
                str(root / "postgres.log"),
                "-o",
                f"-k {root} -c listen_addresses=''",
                "-w",
                "start",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        server = None
        try:
            environment = {
                **os.environ,
                "PGHOST": str(root),
                "PGPORT": "5432",
                "PGUSER": "pf_admin",
                "PGDATABASE": "postgres",
            }
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            db = Database(
                root, f"http://127.0.0.1:{port}", environment, os.urandom(32).hex()
            )
            db.sql(
                "CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; "
                "CREATE ROLE service_role NOLOGIN BYPASSRLS; "
                "CREATE ROLE authenticator LOGIN NOINHERIT; "
                "GRANT anon,authenticated,service_role TO authenticator;"
            )
            subprocess.run(
                [str(ROOT / ".venv/bin/python"), "scripts/migrate.py"],
                cwd=ROOT,
                env=environment,
                check=True,
            )
            settings = {
                **os.environ,
                "PGRST_DB_URI": f"postgresql://authenticator@/postgres?host={root}&port=5432",
                "PGRST_DB_ANON_ROLE": "anon",
                "PGRST_DB_SCHEMAS": "public",
                "PGRST_DB_MAX_ROWS": "3",
                "PGRST_JWT_SECRET": db.secret,
                "PGRST_SERVER_HOST": "127.0.0.1",
                "PGRST_SERVER_PORT": str(port),
            }
            with (root / "postgrest.log").open("wb") as output:
                server = subprocess.Popen(
                    [str(tools / "postgrest")],
                    env=settings,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
            deadline = time.monotonic() + 15
            while True:
                try:
                    db.client("anon").preflight()
                    break
                except ValueError:
                    if time.monotonic() >= deadline:
                        pytest.fail(
                            "disposable PostgREST failed readiness: "
                            + (root / "postgrest.log").read_text()
                        )
                    time.sleep(0.1)
            yield db
        finally:
            if server is not None:
                server.terminate()
                server.wait(timeout=10)
            subprocess.run(
                [
                    str(pg / "pg_ctl"),
                    "-D",
                    str(root / "data"),
                    "-m",
                    "fast",
                    "-w",
                    "stop",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            evidence = ROOT / "artifacts/milestone4/integration"
            evidence.mkdir(parents=True, exist_ok=True)
            for name in ("postgres.log", "postgrest.log"):
                if (root / name).exists():
                    shutil.copy2(root / name, evidence / name)


@pytest.fixture
def frozen_data() -> PreparedData:
    from dataclasses import replace

    from tests.market_fixtures import synthetic_history

    request = RunRequest(
        tickers=("AMD", "MSFT"),
        history_start=date(2026, 7, 1),
        history_end=date(2026, 9, 8),
        mode="retrospective",
        allocation=AllocationSettings(risk_window=2),
        forecast=ForecastSettings(yearly_seasonality=False),
    )
    resolved = request.resolve()
    plan = plan_sessions(resolved)
    assert plan is not None
    return prepare_data(
        resolved,
        plan,
        tuple(
            replace(
                synthetic_history(ticker, plan.sessions, offset=index * 10),
                retrieved_at=utc_now(),
            )
            for index, ticker in enumerate(request.tickers)
        ),
    )
