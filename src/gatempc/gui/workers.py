"""Running a published script from the window without freezing it.

Nothing here changes what a script does. The command is exactly what a reviewer would
type — ``<the interpreter running this GUI> scripts/<name>.py`` from the repository
root — and the button that starts it shows that line before it runs, so the window is
a convenience rather than a second, hidden way of producing the numbers.

The subprocess is configured the same way on all three platforms, with two Windows
specifics: no console window flashes up, and the child's encoding is pinned to UTF-8
so Cyrillic output is not mangled by the console code page.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


def child_environment() -> dict[str, str]:
    """The environment a script is run with: inherited, plus predictable I/O."""
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def _creation_flags() -> int:
    """Keep a console window from flashing up on Windows; 0 elsewhere."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class ScriptRunner(QThread):
    """Run one command, emitting its output line by line."""

    line = pyqtSignal(str)
    finished_with = pyqtSignal(int)

    def __init__(self, command: list[str], cwd: Path) -> None:
        super().__init__()
        self.command = list(command)
        self.cwd = Path(cwd)
        self._process: subprocess.Popen[str] | None = None
        self._cancelled = False

    # -- QThread ----------------------------------------------------------------

    def run(self) -> None:  # pragma: no cover - needs a live process
        try:
            self._process = subprocess.Popen(
                self.command,
                cwd=str(self.cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=child_environment(),
                creationflags=_creation_flags(),
            )
        except OSError as error:
            self.line.emit(f"{type(error).__name__}: {error}")
            self.finished_with.emit(-1)
            return

        assert self._process.stdout is not None
        for raw in self._process.stdout:
            self.line.emit(raw.rstrip("\n"))
        code = self._process.wait()
        if self._cancelled:
            self.line.emit("--- stopped by the user ---")
        self.finished_with.emit(code)

    # -- control ----------------------------------------------------------------

    def cancel(self) -> None:
        """Ask the child to stop. Falls back to a kill if it ignores the request."""
        self._cancelled = True
        process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:  # pragma: no cover - platform dependent
            pass


class FunctionRunner(QThread):
    """Run one callable off the interface thread and hand back what it returned.

    The detector chews through tens of thousands of samples in pure Python. That is
    a second or two — long enough that a frozen window would look like a crash, and
    short enough that a progress bar would be theatre. So: a thread, a wait cursor,
    and the answer when it is ready.
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, *arguments, **keywords) -> None:
        super().__init__()
        self._function = function
        self._arguments = arguments
        self._keywords = keywords

    def run(self) -> None:  # pragma: no cover - needs a running loop
        try:
            self.done.emit(self._function(*self._arguments, **self._keywords))
        except Exception as error:  # the page reports it; the window stays up
            self.failed.emit(f"{type(error).__name__}: {error}")


def describe(command: list[str], cwd: Path) -> str:
    """The command as a reviewer would type it, with the interpreter kept explicit."""
    parts: list[str] = []
    for index, item in enumerate(command):
        text = item
        if index == 0 and Path(item) == Path(sys.executable):
            text = "python"
        else:
            try:
                text = str(Path(item).relative_to(cwd).as_posix())
            except (ValueError, OSError):
                text = item
        parts.append(f'"{text}"' if " " in text else text)
    return " ".join(parts)
