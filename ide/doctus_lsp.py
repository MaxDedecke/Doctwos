"""Übergang doctus→codena (docs/UMBENENNUNG_CODENA.md): alter Startpfad bestehender Editor-Konfigurationen.

Startet unverändert ide/codena_lsp.py.
"""
import os
import runpy

runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "codena_lsp.py"), run_name="__main__")
