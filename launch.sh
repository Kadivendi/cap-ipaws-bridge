#!/usr/bin/env python3
"""
launch.sh — convenience wrapper referenced by README.md.

Despite the ``.sh`` extension this is a Python script: the README invokes it
as ``python launch.sh --sandbox --simulate-feed``. Running ``./launch.sh``
works too because the shebang above resolves to ``python3``.

Spins up the bridge plus the dashboard via ``docker compose``. The flags
consumed here (``--sandbox`` / ``--simulate-feed``) are translated into
environment variables read by the containers; they are NOT forwarded to
``docker compose`` (which does not recognise them and would error out).

Examples
--------
Run with a real IPAWS cert mounted::

    ./launch.sh

Force sandbox mode + use the simulated NOAA / NWS / USGS feeds::

    python launch.sh --sandbox --simulate-feed
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
COMPOSE_FILE = REPO_ROOT / "compose.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launch.sh",
        description="Boot the cap-ipaws-bridge stack via docker compose.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Force IPAWS_SANDBOX=true even if a real cert is mounted.",
    )
    parser.add_argument(
        "--simulate-feed",
        action="store_true",
        help="Hint the bridge to use the simulated NOAA / NWS / USGS feeds.",
    )
    parser.add_argument(
        "--no-detach",
        action="store_true",
        help="Run docker compose in the foreground (do not pass -d).",
    )
    parser.add_argument(
        "compose_args",
        nargs=argparse.REMAINDER,
        help="Additional arguments to forward to `docker compose up`.",
    )
    return parser


def _docker_compose_command() -> list[str]:
    """Resolve which docker compose CLI is available (v2 vs legacy v1)."""
    if shutil.which("docker"):
        # Detect Compose v2 plugin first.
        rc = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        if rc == 0:
            return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    print(
        "error: neither `docker compose` nor `docker-compose` is on PATH.",
        file=sys.stderr,
    )
    sys.exit(127)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    env = os.environ.copy()
    env["IPAWS_SANDBOX"] = "true" if args.sandbox else env.get("IPAWS_SANDBOX", "false")
    env["USE_SIMULATED_FEEDS"] = (
        "true" if args.simulate_feed else env.get("USE_SIMULATED_FEEDS", "false")
    )

    cmd = _docker_compose_command() + ["-f", str(COMPOSE_FILE), "up"]
    if not args.no_detach:
        cmd.append("-d")
    # Drop a leading "--" separator if argparse handed one back to us.
    extra = [a for a in (args.compose_args or []) if a != "--"]
    cmd.extend(extra)

    print(
        f"launching: {' '.join(cmd)}  "
        f"(IPAWS_SANDBOX={env['IPAWS_SANDBOX']}, USE_SIMULATED_FEEDS={env['USE_SIMULATED_FEEDS']})"
    )
    try:
        return subprocess.call(cmd, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
