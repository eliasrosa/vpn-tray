"""Guardrails de arquitetura: as dependências só podem apontar para dentro.

    domain        -> (nada do projeto; só stdlib)
    ports         -> domain
    application   -> domain, ports
    adapters      -> domain, ports, application.errors
    entrypoints   -> qualquer camada (via composition)

E: nada fora de entrypoints/tray pode importar GTK (gi).
"""

import ast
import pathlib

import pytest

PKG = pathlib.Path(__file__).resolve().parent.parent / "vpntray"

ALLOWED = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "application": {"domain", "ports", "application"},
    "adapters": {"domain", "ports", "adapters", "application.errors"},
}


def layer_of(path: pathlib.Path) -> str:
    rel = path.relative_to(PKG)
    return rel.parts[0].removesuffix(".py") if rel.parts else ""


def project_imports(path: pathlib.Path):
    """Módulos do projeto importados por `path`, como 'domain.model' etc."""
    tree = ast.parse(path.read_text())
    rel = path.relative_to(PKG).with_suffix("")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:  # relativo
                base = list(rel.parts[: -node.level]) if node.level <= len(rel.parts) else []
                mod = ".".join(base + ([node.module] if node.module else []))
            elif (node.module or "").startswith("vpntray"):
                mod = node.module.removeprefix("vpntray").lstrip(".")
            else:
                yield ("external", node.module or "")
                continue
            yield ("project", mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("vpntray"):
                    yield ("project", alias.name.removeprefix("vpntray").lstrip("."))
                else:
                    yield ("external", alias.name)


FILES = sorted(p for p in PKG.rglob("*.py"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(PKG)))
def test_camadas_so_dependem_para_dentro(path):
    layer = layer_of(path)
    allowed = ALLOWED.get(layer)
    if allowed is None:  # entrypoints, composition, __init__
        return
    for kind, mod in project_imports(path):
        if kind != "project" or not mod:
            continue
        assert any(mod == a or mod.startswith(a + ".") for a in allowed), (
            f"{path.relative_to(PKG)} ({layer}) não pode importar {mod}"
        )


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(PKG)))
def test_gtk_so_no_icone(path):
    rel = path.relative_to(PKG)
    if rel.parts[:2] == ("entrypoints", "tray"):
        return
    gtk = [m for kind, m in project_imports(path) if kind == "external" and m.split(".")[0] == "gi"]
    assert not gtk, f"{rel} importa GTK; só entrypoints/tray pode"


@pytest.mark.parametrize("path", sorted((PKG / "domain").rglob("*.py")), ids=lambda p: p.name)
def test_dominio_sem_io(path):
    forbidden = {"subprocess", "os", "socket", "shutil", "pathlib", "threading"}
    used = {m.split(".")[0] for kind, m in project_imports(path) if kind == "external"}
    assert not used & forbidden, f"domain/{path.name} faz I/O: {used & forbidden}"


def test_detector_pega_violacoes():
    """Sanidade: os testes acima precisam conseguir ver uma violação."""
    seen = {m for _kind, m in project_imports(PKG / "adapters" / "systemd.py")}
    assert {"application.errors", "domain.model"} <= seen
    fake = PKG / "domain" / "_violacao_tmp.py"
    fake.write_text("from ..adapters.systemd import SystemdServiceManager\nimport subprocess\n")
    try:
        with pytest.raises(AssertionError, match="não pode importar adapters"):
            test_camadas_so_dependem_para_dentro(fake)
        with pytest.raises(AssertionError, match="faz I/O"):
            test_dominio_sem_io(fake)
    finally:
        fake.unlink()
