"""I/O integrado ao laço do GTK: seguir o journal e rodar tarefas em thread."""

from __future__ import annotations

import threading
from collections.abc import Callable

from gi.repository import Gio, GLib

from ...domain.rules import unit_name


class LineReader:
    """Lê stdout de um processo linha a linha sem travar a interface."""

    def __init__(self, argv: list[str], on_line: Callable[[str], None]):
        self.on_line = on_line
        self._buf = ""
        self.proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
        self.stream = self.proc.get_stdout_pipe()
        self.cancel = Gio.Cancellable()
        self._read()

    def _read(self) -> None:
        self.stream.read_bytes_async(8192, GLib.PRIORITY_DEFAULT, self.cancel, self._on_data)

    def _on_data(self, stream, res) -> None:
        try:
            data = stream.read_bytes_finish(res).get_data()
        except GLib.Error:
            return
        if not data:
            return
        self._buf += data.decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for line in lines:
            self.on_line(line)
        self._read()

    def close(self) -> None:
        self.cancel.cancel()
        try:
            self.proc.force_exit()
        except GLib.Error:
            # O processo já tinha terminado: nada a encerrar.
            return


class JournalctlFollower:
    """Porta JournalFollower com `journalctl -f` (precisa do laço do GTK)."""

    def follow_invocation(self, invocation_id: str, on_line: Callable[[str], None]) -> LineReader:
        return LineReader(
            [
                "journalctl",
                f"_SYSTEMD_INVOCATION_ID={invocation_id}",
                "-f",
                "--lines=all",
                "-o",
                "cat",
                "--no-pager",
            ],
            on_line,
        )

    def follow_profile(self, profile: str, on_line: Callable[[str], None]) -> LineReader:
        return LineReader(
            ["journalctl", "-u", unit_name(profile), "-n", "300", "-f", "-o", "short-iso", "--no-pager"],
            on_line,
        )


Done = Callable[[object, Exception | None], None]


def thread_runner(fn: Callable[[], object], done: Done) -> None:
    """Roda `fn` numa thread (systemctl pode esperar a senha) e devolve na UI."""

    def work():
        try:
            result, error = fn(), None
        except Exception as e:  # noqa: BLE001 — repassado para a UI
            result, error = None, e
        GLib.idle_add(lambda: (done(result, error), False)[1])

    threading.Thread(target=work, daemon=True).start()


def inline_runner(fn: Callable[[], object], done: Done) -> None:
    """Versão síncrona (testes e modo demo)."""
    try:
        result, error = fn(), None
    except Exception as e:  # noqa: BLE001 — repassado para quem chamou
        result, error = None, e
    done(result, error)
