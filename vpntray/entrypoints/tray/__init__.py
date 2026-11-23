"""Ícone na bandeja (GTK 3 + XApp/AyatanaAppIndicator).

Fixa as versões das bibliotecas GObject antes de qualquer import do GTK.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Notify", "0.7")
