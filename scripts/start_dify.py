"""一键把本机 Dify 拉起来（Windows / macOS / Linux）。

为什么需要它：Docker Desktop 不会长期保持运行，重启、休眠、掉登录之后站点就「打不开」，
实际原因只是容器没起。这个脚本把「起引擎 → 起容器 → 等端口 → 体检」串成一条命令。

用法：
  python scripts/start_dify.py                  # 起引擎 + 起容器 + 等就绪
  python scripts/start_dify.py --check          # 只体检，不改任何东西
  python scripts/start_dify.py --install-autostart   # 写入登录自启（仅 Windows）

环境变量（都有默认值）：
  DOCKER_COMPOSE_DIR   默认 ../dify/docker
  DIFY_URL             默认 http://127.0.0.1:8080
  MODEL_GATEWAY_URL    可选，例如 http://127.0.0.1:PORT/v1/models；设了就一起体检
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SITE = os.environ.get("DIFY_URL", "http://127.0.0.1:8080").rstrip("/")
SITE_CHECK = SITE + "/console/api/setup"
GATEWAY = os.environ.get("MODEL_GATEWAY_URL", "").strip()
DEFAULT_COMPOSE_DIR = Path(os.environ.get(
    "DOCKER_COMPOSE_DIR",
    Path(__file__).resolve().parent.parent / "dify" / "docker",
))
DOCKER_DESKTOP_CANDIDATES = [
    r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
    "/Applications/Docker.app",
]


def sh(cmd, cwd=None, timeout=600):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def docker_up() -> bool:
    if not shutil.which("docker"):
        return False
    code, _ = sh(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=60)
    return code == 0


def http_ok(url: str, timeout=10) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def report() -> None:
    print("== 状态 ==")
    print("  docker engine   :", "OK" if docker_up() else "DOWN")
    if GATEWAY:
        print("  model gateway   :", "OK" if http_ok(GATEWAY) else "DOWN")
    print("  dify " + SITE + " :", "OK" if http_ok(SITE_CHECK) else "DOWN")


def start_engine() -> bool:
    for exe in DOCKER_DESKTOP_CANDIDATES:
        if Path(exe).exists():
            print("启动 Docker Desktop ...")
            if exe.endswith(".app"):
                subprocess.Popen(["open", "-a", exe], close_fds=True)
            else:
                subprocess.Popen([exe], close_fds=True)
            for _ in range(60):
                time.sleep(5)
                if docker_up():
                    print("  引擎已就绪")
                    return True
            return False
    print("  找不到 Docker Desktop，请手动启动；或确认 docker 在 PATH 里")
    return False


def install_autostart() -> int:
    if os.name != "nt":
        print("仅 Windows 支持自动写登录自启；其他系统请用 systemd / launchd / cron")
        return 1
    startup = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"
    startup.mkdir(parents=True, exist_ok=True)
    lnk = startup / "dify-autostart.lnk"
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{py}';"
        "$s.Arguments='\"{script}\" --timeout 600';"
        "$s.WorkingDirectory='{cwd}';$s.WindowStyle=7;$s.Save()"
    ).format(lnk=str(lnk), py=sys.executable,
             script=str(Path(__file__).resolve()),
             cwd=str(Path(__file__).resolve().parent))
    code, out = sh(["powershell", "-NoProfile", "-Command", ps], timeout=120)
    print("已设置开机自启：" + str(lnk) if code == 0 else "设置失败：" + out[-400:])
    return code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--install-autostart", action="store_true")
    ap.add_argument("--compose-dir", default=str(DEFAULT_COMPOSE_DIR))
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    if args.install_autostart:
        return install_autostart()

    if args.check:
        report()
        return 0 if http_ok(SITE_CHECK) else 1

    if not docker_up() and not start_engine():
        report()
        return 1

    print("拉起 Dify 容器 ...")
    code, out = sh(["docker", "compose", "up", "-d", "--wait"], cwd=args.compose_dir, timeout=900)
    if code != 0:
        code, out = sh(["docker", "compose", "up", "-d"], cwd=args.compose_dir, timeout=900)
        if code != 0:
            print(out[-1500:])
            return 1

    print(f"等 {SITE} 就绪 ...")
    started = time.time()
    while time.time() - started < args.timeout:
        if http_ok(SITE_CHECK):
            print(f"  就绪，用时 {int(time.time() - started)} 秒")
            break
        time.sleep(5)
    else:
        print("  超时：`docker compose ps` 看容器状态，或 `docker logs <nginx 容器>`")
        report()
        return 1

    report()
    print("\n控制台：", SITE + "/apps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
