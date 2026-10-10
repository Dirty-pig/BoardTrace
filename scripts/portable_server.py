"""Entry point for the self-contained Windows distribution."""

import os

from waitress import serve

from app import create_app


if __name__ == "__main__":
    host = os.environ.get("BOARDTRACE_HOST", "127.0.0.1")
    port = int(os.environ.get("BOARDTRACE_PORT", "5000"))
    serve(create_app(), host=host, port=port, threads=8, channel_timeout=120)
