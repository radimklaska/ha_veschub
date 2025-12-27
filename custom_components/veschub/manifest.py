"""Manifest data for VESC Hub BMS integration."""
import json
from pathlib import Path

# Read manifest.json
MANIFEST_PATH = Path(__file__).parent / "manifest.json"
with open(MANIFEST_PATH) as f:
    MANIFEST = json.load(f)
