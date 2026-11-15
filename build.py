"""Сборка в .exe (п.16): pip install -r requirements-build.txt && python build.py
Результат в папке dist/: ITDesk-Server.exe, ITDesk-Client.exe, config.ini, start.bat"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def pyinstaller(*args):
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                           "--specpath", "build", *args], cwd=ROOT)


def main():
    pyinstaller("--onefile", "--name", "ITDesk-Server", "--collect-submodules", "uvicorn", "run_server.py")
    pyinstaller("--onefile", "--windowed", "--name", "ITDesk-Client", "run_client.py")
    dist = ROOT / "dist"
    shutil.copy(ROOT / "config.ini", dist / "config.ini")
    (dist / "start.bat").write_text(
        '@echo off\r\nstart "" "%~dp0ITDesk-Server.exe"\r\ntimeout /t 2 >nul\r\n'
        'start "" "%~dp0ITDesk-Client.exe"\r\n', encoding="ascii")
    print("Готово:", dist)


if __name__ == "__main__":
    main()
