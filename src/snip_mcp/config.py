"""Configuration for snip_mcp."""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Windows virtual key codes for modifier keys
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt

# Modifier flags for RegisterHotKey (also useful for config display)
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_ALT = 0x0001

MODIFIER_MAP = {
    "ctrl": VK_CONTROL,
    "shift": VK_SHIFT,
    "alt": VK_MENU,
}

DEFAULT_CONFIG_DIR = Path.home() / ".snip_mcp"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_SNIPS_DIR = DEFAULT_CONFIG_DIR / "snips"


@dataclass
class SnipConfig:
    modifier_keys: list[str] = field(default_factory=lambda: ["ctrl", "shift"])
    save_directory: str = str(DEFAULT_SNIPS_DIR)
    overlay_alpha: float = 0.3
    selection_color: str = "#00ff00"
    selection_width: int = 2
    max_snips: int = 50

    @property
    def save_path(self) -> Path:
        return Path(self.save_directory).expanduser()

    @property
    def modifier_vk_codes(self) -> list[int]:
        return [MODIFIER_MAP[k] for k in self.modifier_keys if k in MODIFIER_MAP]

    def save(self, path: Path = DEFAULT_CONFIG_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_FILE) -> "SnipConfig":
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()
