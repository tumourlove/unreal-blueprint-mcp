"""Entry point for `python -m unreal_blueprint_mcp` and `uvx unreal-blueprint-mcp`."""

from __future__ import annotations

import argparse

from unreal_blueprint_mcp import __version__


def cli() -> None:
    parser = argparse.ArgumentParser(
        prog="unreal-blueprint-mcp",
        description="Blueprint graph reader for Unreal Engine AI development.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    args = parser.parse_args()
    _run_server()


def _run_server() -> None:
    from unreal_blueprint_mcp.server import main
    main()


if __name__ == "__main__":
    cli()
