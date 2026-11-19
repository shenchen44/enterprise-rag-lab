#!/usr/bin/env python3
"""Local service manager. Start/stop only processes launched by this project."""

from pathlib import Path
import os, sys, subprocess, time, socket, secrets, signal, json, urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
ENV = ROOT / ".env"
LOGS = ROOT / "logs"
PIDS = ROOT / ".pids"
LOGS.mkdir(exist_ok=True)
PIDS.mkdir(exist_ok=True)


def config():
    if not ENV.exists():
        ENV.write_text(
            "JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home\nJAVA_PORT=9080\nAGENT_PORT=9081\nMYSQL_PORT=3308\nPLATFORM_DB_USER=rag\nPLATFORM_DB_PASSWORD="
            + secrets.token_hex(24)
            + "\nMYSQL_ROOT_PASSWORD="
            + secrets.token_hex(32)
            + "\nPLATFORM_JWT_SECRET="
            + secrets.token_hex(32)
            + "\nAGENT_INTERNAL_TOKEN="
            + secrets.token_hex(32)
            + "\nPLATFORM_DEMO=true\n"
        )
        ENV.chmod(0o600)
    env = os.environ.copy()
    for line in ENV.read_text().splitlines():
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    env["RAG_PROJECT_ROOT"] = str(PROJECT)
    env["PLATFORM_STORAGE"] = str(ROOT / "storage")
    env["FRONTEND_DIST"] = (ROOT / "frontend/dist").as_uri() + "/"
    env["AGENT_URL"] = "http://127.0.0.1:" + env["AGENT_PORT"]
    env["PLATFORM_JDBC_URL"] = (
        "jdbc:mysql://127.0.0.1:"
        + env["MYSQL_PORT"]
        + "/rag_platform?useUnicode=true&characterEncoding=UTF-8&serverTimezone=UTC&allowPublicKeyRetrieval=true&sslMode=DISABLED"
    )
    env["PATH"] = (
        env["JAVA_HOME"]
        + "/bin:/Users/zeweishou/.local/bin:/opt/homebrew/bin:"
        + env.get("PATH", "")
    )
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(PROJECT)
    return env


def ready(url, headers=None):
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers or {}), timeout=2
        ) as r:
            return r.status == 200
    except Exception:
        return False


def start_process(name, cmd, cwd, env, url, headers=None):
    pidfile = PIDS / (name + ".pid")
    if ready(url, headers):
        if pidfile.exists():
            print(name + ": already running")
            return
        raise RuntimeError(
            name + " port occupied by an untracked service; refusing to replace it"
        )
    with (LOGS / (name + ".log")).open("ab") as log:
        p = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pidfile.write_text(str(p.pid))
    for _ in range(150):
        if p.poll() is not None:
            raise RuntimeError(name + " exited; inspect logs/" + name + ".log")
        if ready(url, headers):
            print(name + ": ready")
            return
        time.sleep(0.4)
    raise RuntimeError(name + " startup timed out; inspect logs/" + name + ".log")


def main():
    env = config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "build":
        subprocess.run(
            ["npm", "ci", "--no-audit", "--no-fund"],
            cwd=ROOT / "frontend",
            env=env,
            check=True,
        )
        subprocess.run(
            ["npm", "run", "build"], cwd=ROOT / "frontend", env=env, check=True
        )
        subprocess.run(
            ["mvn", "-B", "-ntp", "-s", str(ROOT / "maven-settings.xml"), "package"],
            cwd=ROOT / "backend",
            env=env,
            check=True,
        )
    elif cmd == "start":
        if not (PROJECT / ".venv/bin/python").exists():
            raise RuntimeError("Create the original project Python environment first")
        if (
            not (ROOT / "backend/target/rag-platform-1.0.0.jar").exists()
            or not (ROOT / "frontend/dist/index.html").exists()
        ):
            raise RuntimeError(
                "Run ./start.command --build or python3 scripts/platform.py build first"
            )
        if (
            subprocess.run(
                ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode
            != 0
            and sys.platform == "darwin"
        ):
            subprocess.run(["open", "-a", "Docker"], check=True)
            for _ in range(60):
                if (
                    subprocess.run(
                        ["docker", "info"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).returncode
                    == 0
                ):
                    break
                time.sleep(0.5)
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", "180"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        start_process(
            "agent",
            [
                str(PROJECT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "agent_service.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                env["AGENT_PORT"],
            ],
            PROJECT,
            env,
            env["AGENT_URL"] + "/internal/health",
            {"X-Internal-Token": env["AGENT_INTERNAL_TOKEN"]},
        )
        start_process(
            "backend",
            [
                env["JAVA_HOME"] + "/bin/java",
                "-jar",
                str(ROOT / "backend/target/rag-platform-1.0.0.jar"),
            ],
            ROOT / "backend",
            env,
            "http://127.0.0.1:" + env["JAVA_PORT"] + "/api/health",
        )
        print("Open http://127.0.0.1:" + env["JAVA_PORT"])
    elif cmd == "stop":
        for name in ["backend", "agent"]:
            p = PIDS / (name + ".pid")
            if p.exists():
                pid = int(p.read_text())
                try:
                    info = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "command="],
                        text=True,
                        capture_output=True,
                    ).stdout
                    expected = (
                        "rag-platform-1.0.0.jar"
                        if name == "backend"
                        else "agent_service.app:app"
                    )
                    if expected in info:
                        os.kill(pid, signal.SIGTERM)
                        print(name + ": stopped")
                except ProcessLookupError:
                    pass
                p.unlink(missing_ok=True)
        subprocess.run(["docker", "compose", "stop"], cwd=ROOT, env=env, check=True)
    elif cmd == "status":
        print(
            json.dumps(
                {
                    "web": ready(
                        "http://127.0.0.1:" + env["JAVA_PORT"] + "/api/health"
                    ),
                    "agent": ready(
                        env["AGENT_URL"] + "/internal/health",
                        {"X-Internal-Token": env["AGENT_INTERNAL_TOKEN"]},
                    ),
                },
                indent=2,
            )
        )
        subprocess.run(["docker", "compose", "ps"], cwd=ROOT, env=env, check=True)
    else:
        raise RuntimeError("Use build, start, stop, or status")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", str(e), file=sys.stderr)
        sys.exit(1)
