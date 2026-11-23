import importlib.machinery
import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
needs_display = pytest.mark.skipif(not HAS_DISPLAY, reason="precisa de sessão gráfica")


def load_helper():
    """Carrega o helper root (system/vpn-tray-helper) como módulo."""
    path = os.path.join(ROOT, "system", "vpn-tray-helper")
    loader = importlib.machinery.SourceFileLoader("vpn_tray_helper", path)
    spec = importlib.util.spec_from_loader("vpn_tray_helper", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def system():
    from vpntray.adapters.memory import MemorySystem

    return MemorySystem({"work": "saml", "quebrada": "saml"})


@pytest.fixture
def container(system):
    from vpntray.composition import build_memory

    return build_memory(system)
