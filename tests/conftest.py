import importlib.util
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
needs_display = pytest.mark.skipif(not HAS_DISPLAY, reason="precisa de sessão gráfica")


def load_helper():
    path = os.path.join(ROOT, "system", "vpn-tray-helper")
    loader = importlib.machinery.SourceFileLoader("vpn_tray_helper", path)
    spec = importlib.util.spec_from_loader("vpn_tray_helper", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod
