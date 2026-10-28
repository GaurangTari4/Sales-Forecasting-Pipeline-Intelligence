"""Read-only prerequisite check for local, test, and Compose verification."""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from urllib.parse import urlparse


REQUIRED_MODULES = ("fastapi", "httpx", "psycopg", "pytest", "streamlit", "uvicorn")


def _status(label: str, value: bool, detail: str = "") -> bool:
    print(f"{'PASS' if value else 'MISSING'}  {label}{': ' + detail if detail else ''}")
    return value


def main() -> int:
    ok = True
    ok &= _status("Python", sys.version_info >= (3, 11), sys.version.split()[0])
    for module in REQUIRED_MODULES:
        ok &= _status(f"Python module {module}", importlib.util.find_spec(module) is not None)
    docker = shutil.which("docker")
    ok &= _status("Docker CLI", docker is not None, docker or "install Docker Desktop / Docker Engine with Compose v2")
    url = os.getenv("SALES_FORECAST_TEST_DATABASE_URL")
    if url:
        database = urlparse(url).path.lstrip("/")
        safe = url.startswith(("postgres://", "postgresql://")) and database.endswith("_test")
        ok &= _status("Disposable PostgreSQL test database", safe, database or "invalid URL")
    else:
        print("MISSING  Disposable PostgreSQL test database: set SALES_FORECAST_TEST_DATABASE_URL to a database whose name ends in _test")
        ok = False
    if not ok:
        print("\nInstall Python requirements with: python -m pip install -r requirements.txt")
        print("Docker and a disposable PostgreSQL test database are required for full integration verification.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
