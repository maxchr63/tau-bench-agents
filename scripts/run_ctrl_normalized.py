"""Start AgentBeats controller with isolated state + canonical URLs.

This wrapper runs the controller from an isolated working directory (derived
from ROLE/PORT) so running *two* controllers locally doesn't clobber `.ab/agents`.

It also normalizes the controller's externally-reachable host config so generated
agent URLs don't contain accidental `//to_agent/...` (e.g. if `CLOUDRUN_HOST` was
provided with a trailing slash).

Run (example):
  PORT=8010 CLOUDRUN_HOST=<host> HTTPS_ENABLED=true ROLE=green uv run python scripts/run_ctrl_normalized.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


class NormalizeSlashesMiddleware:
    """ASGI middleware that collapses repeated slashes in the request path.

    This prevents 404s when a client accidentally hits URLs like `//to_agent/...`.
    """

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            normalized = re.sub(r"/{2,}", "/", path)
            if normalized != path:
                scope = dict(scope)
                scope["path"] = normalized
                scope["raw_path"] = normalized.encode("utf-8")
        await self.app(scope, receive, send)


def _ensure_isolated_workdir(repo_root: Path) -> Path:
    role = (os.environ.get("ROLE") or os.environ.get("AGENT") or "default").strip().lower() or "default"
    port = (os.environ.get("PORT") or "8010").strip() or "8010"

    workdir = repo_root / ".ab" / "controllers" / f"{role}_{port}"
    workdir.mkdir(parents=True, exist_ok=True)

    # The controller expects to find and execute ./run.sh from its cwd.
    run_sh = workdir / "run.sh"
    run_sh.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "",
                f"cd \"{repo_root}\"",
                "exec uv run python main.py run",
                "",
            ]
        )
    )
    run_sh.chmod(0o755)
    return workdir


def _sanitize_cloudrun_host_env() -> None:
    # The controller treats CLOUDRUN_HOST as a host (no scheme, no trailing slash).
    # If it ends with '/', generated URLs become `https://<host>//to_agent/...`.
    v = os.environ.get("CLOUDRUN_HOST")
    if not v:
        return

    v = v.strip()
    if v.startswith("https://"):
        v = v.removeprefix("https://")
    elif v.startswith("http://"):
        v = v.removeprefix("http://")
    v = v.rstrip("/")
    os.environ["CLOUDRUN_HOST"] = v


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    workdir = _ensure_isolated_workdir(repo_root)
    os.chdir(workdir)

    _sanitize_cloudrun_host_env()

    from agentbeats import controller

    controller.app.add_middleware(NormalizeSlashesMiddleware)
    controller.main()


if __name__ == "__main__":
    main()
