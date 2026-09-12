"""Build sdist -> wheel, then install locked runtime dependencies into a fresh venv."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv", help="Pinned uv executable")
    uv: str = parser.parse_args().uv
    with TemporaryDirectory(prefix="portfolio-package-smoke-") as directory:
        temporary = Path(directory)
        distributions = temporary / "dist"
        environment = temporary / "venv"
        requirements = temporary / "runtime.txt"
        # The default build creates the wheel from the sdist, testing both artifacts.
        run([uv, "build", "--out-dir", str(distributions)])
        wheels = list(distributions.glob("*.whl"))
        sdists = list(distributions.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise RuntimeError("Expected one source distribution and one wheel")
        run(
            [
                uv,
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ]
        )
        run([uv, "venv", "--python", sys.executable, str(environment)])
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        run(
            [
                uv,
                "pip",
                "sync",
                "--python",
                str(python),
                "--require-hashes",
                str(requirements),
            ]
        )
        run(
            [uv, "pip", "install", "--python", str(python), "--no-deps", str(wheels[0])]
        )
        # -I and a different working directory prevent a source-tree import from
        # disguising a broken distribution or a dependency on developer tools.
        run(
            [
                str(python),
                "-I",
                "-c",
                """
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
import portfolio_forecasting
from portfolio_forecasting import RunRequest
package = Path(portfolio_forecasting.__file__).resolve()
assert package.is_relative_to(Path(sys.prefix).resolve()), package
assert package.with_name('py.typed').is_file()
assert version('portfolio-forecasting') == '0.1.0'
assert find_spec('pytest') is None
assert find_spec('mypy') is None
resolved = RunRequest().resolve(clock=lambda: datetime(2026, 9, 12, 9, tzinfo=UTC))
metadata = json.loads(json.dumps(resolved.to_metadata(), allow_nan=False))
assert metadata['history_end'] == '2026-09-12'
assert len(metadata['tickers']) == 12
print('PASS: sdist/wheel, locked runtime-only install, isolated request resolution')
""",
            ],
            cwd=temporary,
        )


if __name__ == "__main__":
    main()
