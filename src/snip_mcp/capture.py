"""Screen region capture using mss + Pillow."""

import io
from datetime import datetime
from pathlib import Path

import mss
from PIL import Image


def capture_region(x: int, y: int, width: int, height: int) -> bytes:
    """Capture a screen region and return PNG bytes.

    Coordinates are in physical (DPI-aware) screen pixels.
    """
    region = {"left": x, "top": y, "width": width, "height": height}
    with mss.mss() as sct:
        raw = sct.grab(region)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def save_snip(png_bytes: bytes, save_dir: Path, name: str | None = None) -> Path:
    """Save PNG bytes to disk. Returns the file path.

    If name is None, auto-generates from timestamp.
    """
    save_dir.mkdir(parents=True, exist_ok=True)
    if name is None:
        name = f"snip_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not name.endswith(".png"):
        name += ".png"
    path = save_dir / name
    path.write_bytes(png_bytes)
    return path


if __name__ == "__main__":
    # Quick test: capture a 200x200 region from top-left of primary monitor
    data = capture_region(0, 0, 200, 200)
    out = save_snip(data, Path.home() / ".snip_mcp" / "snips")
    print(f"Saved test snip: {out} ({len(data)} bytes)")
