"""Manifest data for VESC Hub BMS integration."""
import json
from pathlib import Path

# Load manifest at module import time (before async event loop starts)
MANIFEST_PATH = Path(__file__).parent / "manifest.json"
with MANIFEST_PATH.open() as f:
    MANIFEST = json.load(f)
