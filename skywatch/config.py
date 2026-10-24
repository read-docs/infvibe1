import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    port: int = 8080
    nasa_api_key: str = "DEMO_KEY"


def load_config(path: Path) -> Config:
    """Reads config.json; a missing file or fields fall back to defaults."""
    cfg = Config()
    try:
        text = path.read_text()
    except OSError:
        print(f"warning: {path} not found, using defaults (DEMO_KEY)", file=sys.stderr)
        return cfg
    data = json.loads(text)
    cfg.port = int(data.get("port", cfg.port))
    cfg.nasa_api_key = str(data.get("nasa_api_key", cfg.nasa_api_key))
    return cfg
