"""Apply checksummed SQL using psql and an explicit libpq connection environment."""

import argparse
import hashlib
import os
import subprocess
from pathlib import Path


def migrate(directory: Path, *, environment: dict[str, str] | None = None) -> None:
    connection = os.environ if environment is None else environment
    if not connection.get("PGSERVICE") and not all(
        connection.get(name) for name in ("PGHOST", "PGDATABASE", "PGUSER")
    ):
        raise RuntimeError(
            "migration requires an explicit PGSERVICE or PGHOST/PGDATABASE/PGUSER"
        )
    files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError("no versioned SQL migrations found")
    for path in files:
        version = int(path.name.split("_", 1)[0])
        sql = path.read_text()
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        prefix = f"""
BEGIN;
SELECT pg_advisory_xact_lock(740019);
CREATE SCHEMA IF NOT EXISTS pf_private;
CREATE TABLE IF NOT EXISTS pf_private.schema_migrations (
 version integer PRIMARY KEY, sha256 text NOT NULL,
 applied_at timestamptz NOT NULL DEFAULT clock_timestamp());
DO $$ BEGIN
 IF EXISTS(SELECT FROM pf_private.schema_migrations
           WHERE version={version} AND sha256<>'{checksum}') THEN
   RAISE EXCEPTION 'applied migration checksum differs';
 END IF;
END $$;
SELECT NOT EXISTS(SELECT FROM pf_private.schema_migrations
                  WHERE version={version}) AS pf_apply \gset
\if :pf_apply
"""
        suffix = f"""
INSERT INTO pf_private.schema_migrations(version,sha256) VALUES({version},'{checksum}');
\endif
COMMIT;
"""
        result = subprocess.run(
            ["psql", "-X", "--no-password", "-v", "ON_ERROR_STOP=1", "-q"],
            input=prefix + sql + suffix,
            text=True,
            capture_output=True,
            env=environment,
        )
        if result.returncode:
            # Migration text contains no credentials. Connection error details are
            # withheld because libpq may include connection information.
            raise RuntimeError(
                f"migration {path.name} failed (psql exit {result.returncode})"
            )
        print(f"PASS: migration {path.name} checksum={checksum}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrations", type=Path, default=Path("supabase/migrations"))
    args = parser.parse_args()
    migrate(args.migrations)


if __name__ == "__main__":
    main()
