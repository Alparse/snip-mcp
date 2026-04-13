"""Thread-safe snip storage with disk persistence."""

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass
class SnipInfo:
    name: str
    timestamp: datetime
    file_path: Path
    size_bytes: int


class SnipStore:
    """Named snip storage with disk persistence and auto-pruning."""

    def __init__(self, save_dir: Path, max_snips: int = 50):
        self.save_dir = save_dir
        self.max_snips = max_snips
        self._lock = threading.Lock()
        self._snips: dict[str, SnipInfo] = {}
        self._next_id = 1
        self.on_new_snip: Callable[[str, SnipInfo], None] | None = None

        self.save_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self):
        """Load existing snips from disk and set next ID."""
        max_id = 0
        for f in sorted(self.save_dir.glob("*.png"), key=lambda p: p.stat().st_mtime):
            name = f.stem
            stat = f.stat()
            self._snips[name] = SnipInfo(
                name=name,
                timestamp=datetime.fromtimestamp(stat.st_mtime),
                file_path=f,
                size_bytes=stat.st_size,
            )
            # Track highest numeric ID for sequential naming
            if name.startswith("snip_"):
                try:
                    num = int(name.split("_", 1)[1])
                    max_id = max(max_id, num)
                except ValueError:
                    pass
        self._next_id = max_id + 1

    def add(self, png_bytes: bytes, name: str | None = None) -> SnipInfo:
        """Store a new snip. Returns its info."""
        with self._lock:
            if name is None:
                name = f"snip_{self._next_id}"
                self._next_id += 1

            # Deduplicate name if needed
            base_name = name
            counter = 1
            while name in self._snips:
                name = f"{base_name}_{counter}"
                counter += 1

            file_path = self.save_dir / f"{name}.png"
            file_path.write_bytes(png_bytes)

            info = SnipInfo(
                name=name,
                timestamp=datetime.now(),
                file_path=file_path,
                size_bytes=len(png_bytes),
            )
            self._snips[name] = info

            self._prune()

            if self.on_new_snip:
                self.on_new_snip(name, info)

            return info

    def get(self, name: str) -> bytes | None:
        """Retrieve snip PNG bytes by name."""
        with self._lock:
            info = self._snips.get(name)
            if info and info.file_path.exists():
                return info.file_path.read_bytes()
            return None

    def get_info(self, name: str) -> SnipInfo | None:
        """Get metadata for a snip."""
        with self._lock:
            return self._snips.get(name)

    def get_latest(self) -> tuple[str, bytes] | None:
        """Get the most recent snip (name, bytes)."""
        with self._lock:
            if not self._snips:
                return None
            name = max(self._snips, key=lambda k: self._snips[k].timestamp)
            info = self._snips[name]
            if info.file_path.exists():
                return name, info.file_path.read_bytes()
            return None

    def list_snips(self) -> list[SnipInfo]:
        """List all snips, newest first."""
        with self._lock:
            return sorted(
                self._snips.values(),
                key=lambda s: s.timestamp,
                reverse=True,
            )

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a snip. Returns True on success."""
        with self._lock:
            if old_name not in self._snips or new_name in self._snips:
                return False
            info = self._snips.pop(old_name)
            new_path = self.save_dir / f"{new_name}.png"
            info.file_path.rename(new_path)
            info.name = new_name
            info.file_path = new_path
            self._snips[new_name] = info
            return True

    def delete(self, name: str) -> bool:
        """Delete a snip. Returns True on success."""
        with self._lock:
            info = self._snips.pop(name, None)
            if info and info.file_path.exists():
                info.file_path.unlink()
                return True
            return False

    def _prune(self):
        """Remove oldest snips if over max_snips limit."""
        while len(self._snips) > self.max_snips:
            oldest = min(self._snips, key=lambda k: self._snips[k].timestamp)
            info = self._snips.pop(oldest)
            if info.file_path.exists():
                info.file_path.unlink()
