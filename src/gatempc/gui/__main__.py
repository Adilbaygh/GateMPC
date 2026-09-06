"""``python -m gatempc.gui`` — the same explorer, when the package is installed."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(program="python -m gatempc.gui"))
