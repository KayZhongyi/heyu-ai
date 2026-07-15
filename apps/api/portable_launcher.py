from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def bundle_root() -> Path:
    """Return the directory containing resources added by PyInstaller."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent


def application_root() -> Path:
    """Keep mutable application data beside the portable executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def configure_environment() -> Path:
    root = application_root()
    os.chdir(root)
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    database_path = (data_dir / "heyu.db").resolve().as_posix()

    os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
    os.environ["AUTO_CREATE_SCHEMA"] = "false"
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("PYTHONUTF8", "1")
    return data_dir


def migrate_database() -> None:
    from alembic import command
    from alembic.config import Config

    resources = bundle_root()
    config = Config(str(resources / "alembic.ini"))
    config.set_main_option("script_location", str(resources / "migrations"))
    command.upgrade(config, "head")


def wait_and_open(url: str, *, open_browser: bool) -> None:
    health_url = f"{url.rstrip('/')}/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    if open_browser:
                        webbrowser.open(url)
                    print(f"禾语 AI 已启动：{url}", flush=True)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    print("禾语 AI 启动超时，请关闭窗口后重试。", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动禾语 AI Windows 便携版")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_environment()
    print("正在准备禾语 AI 本地数据……", flush=True)
    migrate_database()

    import uvicorn

    from app.main import app

    url = f"http://{args.host}:{args.port}/"
    browser_thread = threading.Thread(
        target=wait_and_open,
        kwargs={"url": url, "open_browser": not args.no_browser},
        daemon=True,
    )
    browser_thread.start()

    print("正在启动禾语 AI。关闭此窗口即可停止平台。", flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
