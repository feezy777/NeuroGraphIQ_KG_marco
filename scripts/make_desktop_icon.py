# Regenerate scripts/icons/neurographiq-brain.ico from the source PNG.
# Usage: backend/.venv/Scripts/python.exe scripts/make_desktop_icon.py
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "icons" / "brain-source.png"
OUT = ROOT / "icons" / "neurographiq-brain.ico"

img = Image.open(SRC).convert("RGBA")
img.save(
    OUT,
    format="ICO",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print(f"written: {OUT}")
