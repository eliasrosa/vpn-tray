"""VPN Tray: bandeja, CLI e MCP para o openfortivpn (arquitetura hexagonal).

Camadas (dependências só apontam para dentro):

    entrypoints  ->  application  ->  domain
         |               |
         +--> adapters --+--> ports (contratos)

Veja docs/architecture.md.
"""

from pathlib import Path


def _read_version() -> str:
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
    except OSError:
        return "0.0.0"


__version__ = _read_version()
