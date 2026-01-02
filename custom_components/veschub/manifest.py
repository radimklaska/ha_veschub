"""Manifest data for VESC Hub BMS integration."""
import json
from pathlib import Path
from functools import lru_cache

MANIFEST_PATH = Path(__file__).parent / "manifest.json"

@lru_cache(maxsize=1)
def get_manifest() -> dict:
    """Load manifest.json (cached after first call)."""
    with MANIFEST_PATH.open() as f:
        return json.load(f)

# For backward compatibility
def __getattr__(name):
    """Lazy load MANIFEST attribute."""
    if name == "MANIFEST":
        return get_manifest()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
