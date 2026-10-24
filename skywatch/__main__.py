"""python3 -m skywatch [--port N]: serves the app at http://localhost:8080"""

import argparse
import sys
from pathlib import Path

from skywatch.config import load_config
from skywatch.server import SkyWatch, make_server

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(prog="python3 -m skywatch", description="SkyWatch web server")
    parser.add_argument("--port", type=int, help="overrides the port in config.json")
    args = parser.parse_args()

    cfg = load_config(ROOT / "config.json")
    port = args.port or cfg.port
    web_root = ROOT / "web"
    if not web_root.is_dir():
        print(f"error: web directory not found: {web_root}", file=sys.stderr)
        return 1

    try:
        server = make_server(SkyWatch(cfg, ROOT), web_root, "127.0.0.1", port)
    except OSError as e:
        print(f"error: could not listen on port {port}: {e}", file=sys.stderr)
        return 1
    print(f"SkyWatch running at http://localhost:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
