"""User configuration (defaults for CLI flags and GUI settings).

Stored as JSON in the platform's config directory, or wherever the
``CALEL_CONFIG`` environment variable points.  A missing or unreadable file
simply means "use the built-in defaults".
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from calel.core.calculator import Options


@dataclass
class Config:
    # calculation defaults
    series: str = "E24"
    tolerance: Optional[float] = None
    cap_series: Optional[str] = None
    cap_tolerance: Optional[float] = None
    solutions: int = 5
    rank: str = "error"
    impedance: float = 10e3
    prefer_low_values: bool = False
    r_min: float = 10.0
    r_max: float = 1e6
    c_min: float = 10e-12
    c_max: float = 100e-6
    # CLI
    color: str = "auto"
    format: str = "table"
    # GUI
    theme: str = "light"  # light | dark | high_contrast
    font_size: int = 10

    def to_options(self) -> Options:
        names = {f.name for f in fields(Options)}
        return Options(**{k: v for k, v in asdict(self).items() if k in names})


def config_path() -> Path:
    env = os.environ.get("CALEL_CONFIG")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "calel" / "config.json"


def load(path: Optional[Path] = None) -> Config:
    """Load the config, falling back to defaults for anything missing/invalid."""
    path = path or config_path()
    cfg = Config()
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if not isinstance(data, dict):
        return cfg
    defaults = asdict(cfg)
    for key, value in data.items():
        if key not in defaults:
            continue
        default = defaults[key]
        if default is None or value is None or isinstance(value, type(default)):
            setattr(cfg, key, value)
        elif isinstance(default, float) and isinstance(value, int):
            setattr(cfg, key, float(value))
    return cfg


def save(cfg: Config, path: Optional[Path] = None) -> Path:
    path = Path(path or config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    return path
