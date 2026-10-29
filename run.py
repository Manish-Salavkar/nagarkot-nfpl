import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Run both backend and frontend concurrently
def main():
    root_dir = Path(__file__).resolve().parent
    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"

    venv_python = backend_dir / ".venv" / "bin" / "python3"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    print("\nStarting NFPL Access Control Service...")
    print("Backend:  http://localhost:8000")
    print("Frontend: http://localhost:8002\n")

    # Start FastAPI backend
    backend_process = subprocess.Popen(
        [python_cmd, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(backend_dir),
    )

    # Start Vite frontend on port 8002
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", "8002"],
        cwd=str(frontend_dir),
    )

    # Handle graceful shutdown
    def shutdown(signum, frame):
        print("\nStopping services...")
        try:
            backend_process.terminate()
            frontend_process.terminate()
            backend_process.wait(timeout=5)
            frontend_process.wait(timeout=5)
        except Exception:
            backend_process.kill()
            frontend_process.kill()
        print("Services stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            time.sleep(1)
            if backend_process.poll() is not None:
                print("Backend exited unexpectedly.")
                shutdown(None, None)
            if frontend_process.poll() is not None:
                print("Frontend exited unexpectedly.")
                shutdown(None, None)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
