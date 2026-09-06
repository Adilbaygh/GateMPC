"""Open the GateMPC results explorer.

    python main.py                       open the window
    python main.py --language en         open it in English
    python main.py --page prereg         open it on the pre-registration record
    python main.py --list-pages          print the page keys and exit
    python main.py --screenshot out.png  write one page to a file and exit

The same command works on Windows, macOS and Linux. Nothing here computes a result:
every number the window shows is read from ``results/``, and every button in it runs
one of the published scripts in ``scripts/``.

This file only puts ``src/`` on the import path so that the explorer runs straight from
a clone, with nothing installed. The command line itself lives in
``gatempc.gui.cli``, which is also what the ``gatempc-gui`` console script and
``python -m gatempc.gui`` use.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gatempc.gui.cli import main  # noqa: E402  (the path bootstrap has to come first)

if __name__ == "__main__":
    raise SystemExit(main())
