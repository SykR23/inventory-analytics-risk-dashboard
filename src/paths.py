"""
Locate the folder that holds the *editable* files (config.yaml and data/).

When running from source this is the project root. When running as a frozen
PyInstaller .exe it is the folder that contains the .exe — so a non-technical
user can drop their data/ folder and edit config.yaml right next to the program,
and the cache (data/_processed) persists there too.
"""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):          # running inside a PyInstaller bundle
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve(path_like, default: str) -> Path:
    """Resolve a configured path against base_dir() unless it is absolute."""
    p = Path(path_like) if path_like else Path(default)
    return p if p.is_absolute() else base_dir() / p
