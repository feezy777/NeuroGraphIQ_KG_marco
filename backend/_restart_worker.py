"""Detached restart worker for the NeuroGraphIQ backend (dev-only).

Launched by ``server_restart_service``. It waits for the old process to die and
the port to free, then relaunches ``run_server.py`` via PowerShell
``Start-Process`` (hidden window, logs to files) and supervises it: if the
backend process disappears, the worker relaunches it automatically.

Argv: <old_pid> <port> <run_server_path> <backend_dir> <log_file>
"""

from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import time


_CREATE_NO_WINDOW = 0x08000000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _wait_port_free(port: int, attempts: int = 120, interval: float = 0.25) -> bool:
    for _ in range(attempts):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            s.close()
            time.sleep(interval)
    return False


def _pid_alive(pid: int) -> bool:
    """Return True if a Windows process with the given PID is still running."""
    handle = ctypes.windll.kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
    )
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _port_in_use(port: int) -> bool:
    """Return True if something is already listening on the port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return False
    except OSError:
        s.close()
        return True


def _start_server_via_powershell(
    python_exe: str,
    run_server: str,
    backend_dir: str,
    port: int,
    log_file: str,
    err_file: str,
) -> int | None:
    """Relaunch run_server.py via PowerShell Start-Process (hidden, logs to files).

    Start-Process is the launch method that has proven to survive in this
    environment; a plain DETACHED_PROCESS child of the worker gets silently
    reaped. Returns the launcher PID, or None if the launch failed.
    """
    ps_script = (
        "$p = Start-Process -FilePath '{python_exe}' "
        "-ArgumentList 'run_server.py','{port}' "
        "-WorkingDirectory '{backend_dir}' "
        "-WindowStyle Hidden "
        "-RedirectStandardOutput '{log_file}' "
        "-RedirectStandardError '{err_file}' "
        "-PassThru; "
        "Write-Output $p.Id"
    ).format(
        python_exe=python_exe.replace("'", "''"),
        port=port,
        backend_dir=backend_dir.replace("'", "''"),
        log_file=log_file.replace("'", "''"),
        err_file=err_file.replace("'", "''"),
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = (result.stdout or b"").decode(errors="replace").strip()
    try:
        return int(text.splitlines()[-1])
    except (ValueError, IndexError):
        return None


def main() -> None:
    if len(sys.argv) < 6:
        return
    old_pid = int(sys.argv[1])
    port = int(sys.argv[2])
    run_server = sys.argv[3]
    backend_dir = sys.argv[4]
    log_file = sys.argv[5]

    # Give the old server a moment to flush its HTTP response + self-exit.
    # taskkill below is authoritative, so a short grace period is enough.
    time.sleep(0.6)

    if sys.platform == "win32":
        # CREATE_NO_WINDOW: never flash a cmd/console window from the detached worker.
        subprocess.run(
            ["taskkill", "/PID", str(old_pid), "/F"],
            creationflags=_CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.kill(old_pid, 15)
        except (ProcessLookupError, PermissionError):
            pass

    _wait_port_free(port)

    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    except OSError:
        pass

    # Keep the worker's own supervision log separate: Start-Process redirection
    # truncates its target file, which would wipe the supervisor history.
    server_out_file = os.path.splitext(log_file)[0] + ".server.log"
    server_err_file = os.path.splitext(log_file)[0] + ".server.err.log"
    log = open(log_file, "ab", buffering=0)
    log.write(f"\n===== restart relaunch port={port} (supervised) =====\n".encode())

    launcher_pid = _start_server_via_powershell(
        sys.executable, run_server, backend_dir, port, server_out_file, server_err_file
    )
    log.write(f"[restart] first launch launcher_pid={launcher_pid}\n".encode())

    # Supervisor loop: if the backend process disappears (it has been silently
    # reaped in this environment), relaunch it instead of leaving the API down.
    relaunch_count = 0
    max_relaunches = 120
    while True:
        if launcher_pid is None:
            time.sleep(2)
            launcher_pid = _start_server_via_powershell(
                sys.executable, run_server, backend_dir, port, server_out_file, server_err_file
            )
            log.write(
                f"[restart] relaunch #{relaunch_count} launcher_pid={launcher_pid}\n".encode()
            )
            continue

        # Poll every 5s in 60s windows; keep waiting while the process lives.
        deadline = time.time() + 60
        alive = True
        while time.time() < deadline:
            if not _pid_alive(launcher_pid):
                alive = False
                break
            time.sleep(5)
        if alive:
            continue

        relaunch_count += 1
        log.write(
            f"[restart] backend launcher {launcher_pid} exited; "
            f"relaunch #{relaunch_count}\n".encode()
        )
        if relaunch_count > max_relaunches:
            log.write(b"[restart] max relaunches reached; supervisor stopping\n")
            break
        if _port_in_use(port):
            # A newer restart generation already owns the port; this supervisor's
            # work is done and it must exit instead of spawning competing servers.
            log.write(b"[restart] port already owned by another server; supervisor exiting\n")
            break
        launcher_pid = None


if __name__ == "__main__":
    main()
