"""Execução de processos (único ponto que chama subprocess nos adaptadores)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str], *, timeout: float = 15, input_text: str | None = None) -> Result:
    try:
        r = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, input=input_text, check=False
        )
        return Result(r.returncode, r.stdout, r.stderr.strip())
    except FileNotFoundError as e:
        return Result(127, "", str(e))
    except subprocess.TimeoutExpired:
        return Result(124, "", "tempo esgotado")
