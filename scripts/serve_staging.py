"""Local-only staging listener for checking a new release before port 5000 cutover."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from waitress import serve

from app import create_app


if __name__ == "__main__":
    serve(create_app(), host="127.0.0.1", port=5101, threads=4)
