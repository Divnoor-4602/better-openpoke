from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "generated" / "openapi.json"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.app import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI schema")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()
