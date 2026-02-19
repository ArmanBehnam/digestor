"""
Docker container entrypoint.
Routes to web (FastAPI) or worker (RQ) based on PROCESS_TYPE env var.
Runs Alembic migrations before starting the web server.
"""

import os
import sys
import subprocess


def main():
    process_type = os.getenv("PROCESS_TYPE", "web").lower()

    if process_type == "web":
        print("[ENTRYPOINT] Starting web server (FastAPI)...")

        # Run Alembic migrations
        print("[ENTRYPOINT] Running database migrations...")
        result = subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(__file__),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"[ENTRYPOINT] Migration warning: {result.stderr}")
        else:
            print("[ENTRYPOINT] Migrations complete")

        # Start uvicorn
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8080"))
        workers = int(os.getenv("WEB_WORKERS", "1"))

        os.execvp("uvicorn", [
            "uvicorn",
            "api.main:app",
            "--host", host,
            "--port", str(port),
            "--workers", str(workers),
            "--log-level", "info",
            "--access-log",
        ])

    elif process_type == "worker":
        print("[ENTRYPOINT] Starting RQ worker...")
        # Import and run worker
        from worker import run_worker
        run_worker()

    else:
        print(f"[ENTRYPOINT] Unknown PROCESS_TYPE: {process_type}")
        print("[ENTRYPOINT] Valid options: web, worker")
        sys.exit(1)


if __name__ == "__main__":
    main()
