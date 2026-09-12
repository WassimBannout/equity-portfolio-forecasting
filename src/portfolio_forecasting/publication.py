"""Explicit environment validation only; storage clients and writes belong to M4."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationSettings:
    """Separate from scientific settings; never include credentials in run metadata."""

    url: str
    key: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.url, str)
            or not self.url
            or any(c.isspace() for c in self.url)
        ):
            raise ValueError("SUPABASE_URL must be a valid base URL")
        try:
            parsed = urlsplit(self.url)
            port = parsed.port
            valid = (
                bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and parsed.path in ("", "/")
                and (port is None or 1 <= port <= 65535)
                and (
                    parsed.scheme == "https"
                    or (
                        parsed.scheme == "http"
                        and parsed.hostname in ("localhost", "127.0.0.1", "::1")
                    )
                )
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "SUPABASE_URL requires HTTPS, or HTTP on a loopback test host"
            )
        if (
            not isinstance(self.key, str)
            or not self.key
            or any(c.isspace() for c in self.key)
        ):
            raise ValueError(
                "SUPABASE_KEY must be a nonempty credential without whitespace"
            )

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> PublicationSettings:
        """Read only the explicitly supplied mapping or current process environment."""
        source = os.environ if environment is None else environment
        missing = [
            name for name in ("SUPABASE_URL", "SUPABASE_KEY") if not source.get(name)
        ]
        if missing:
            raise ValueError("missing publication settings: " + ", ".join(missing))
        return cls(url=source["SUPABASE_URL"], key=source["SUPABASE_KEY"])
