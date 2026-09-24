import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from waitress import serve

from app import create_app


if __name__ == "__main__":
    host = os.environ.get("BOARDTRACE_HOST", "0.0.0.0")
    port = int(os.environ.get("BOARDTRACE_PORT", "5000"))
    serve(create_app(), host=host, port=port, threads=8, channel_timeout=120)
