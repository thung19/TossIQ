"""Local dev launcher for the TossIQ API with automatic port fallback.

`uvicorn api:app --port 8000` fails outright if port 8000 is already taken
by some unrelated process. This script tries port 8000 first and, if it's
busy, walks forward through a small range of fallback ports until it finds
one that's free -- so you don't have to hunt for a free port by hand.

Run locally:
    python run_api.py

For a fixed port (no fallback), use uvicorn directly as always:
    uvicorn api:app --reload
"""

import socket
import sys

import uvicorn

HOST = "127.0.0.1"
START_PORT = 8000
END_PORT = 8010


def find_free_port(host: str, start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(
        f"No free port found in range {start}-{end} on {host}. "
        "Free one of these ports, or run `uvicorn api:app --port <port>` "
        "with an explicit port outside this range."
    )


def main() -> None:
    try:
        port = find_free_port(HOST, START_PORT, END_PORT)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Bound to port {port}")
    print(f"Dashboard: http://{HOST}:{port}/")
    uvicorn.run("api:app", host=HOST, port=port)


if __name__ == "__main__":
    main()
