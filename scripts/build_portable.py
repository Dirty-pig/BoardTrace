"""Build and zip the Windows portable release without bundling user data."""

from hashlib import sha256
from pathlib import Path
from shutil import copy2
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "data" / "portable-build"
DIST = BUILD / "dist" / "BoardTrace"
OUTPUT = ROOT / "BoardTrace-Windows-x64.zip"
MANIFEST = ROOT / "BoardTrace-Windows-x64-IT-hashes.txt"


def main():
    if sys.platform != "win32":
        raise SystemExit("Build this package on Windows x64.")

    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "BoardTrace", "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'app' / 'templates'};app/templates",
        "--add-data", f"{ROOT / 'prototype'};prototype",
        "--workpath", str(BUILD / "work"),
        "--distpath", str(BUILD / "dist"),
        "--specpath", str(BUILD / "spec"),
    ]
    sqlite_dll = Path(sys.prefix) / "Library" / "bin" / "sqlite3.dll"
    if sqlite_dll.is_file():
        command += ["--add-binary", f"{sqlite_dll};."]
    command.append(str(ROOT / "scripts" / "portable_server.py"))
    subprocess.run(command, cwd=ROOT, check=True)

    for name in (
        "portable_launch.ps1", "portable_stop.ps1", "portable_diagnose.ps1",
        "启动板迹便携版.cmd", "停止板迹便携版.cmd", "检查启动拦截便携版.cmd",
        "便携版使用说明.txt",
    ):
        copy2(ROOT / "scripts" / name, DIST / name)

    with ZipFile(OUTPUT, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in DIST.rglob("*"):
            if path.is_file() and "data" not in path.relative_to(DIST).parts:
                archive.write(path, (Path("BoardTrace") / path.relative_to(DIST)).as_posix())

    with ZipFile(OUTPUT) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Portable ZIP integrity check failed.")
        if any(name.startswith("BoardTrace/data/") for name in archive.namelist()):
            raise RuntimeError("Portable ZIP unexpectedly contains user data.")
        binaries = sorted(name for name in archive.namelist() if name.lower().endswith((".exe", ".dll", ".pyd")))
        hashes = [(name, sha256(archive.read(name)).hexdigest().upper()) for name in binaries]
    exe_hash = dict(hashes)["BoardTrace/BoardTrace.exe"]
    lines = [
        "BoardTrace Windows x64 portable release — IT verification manifest",
        f"ZIP SHA256: {sha256(OUTPUT.read_bytes()).hexdigest().upper()}",
        f"BoardTrace.exe SHA256: {exe_hash}",
        f"Executable/binary count: {len(hashes)}", "",
        "The custom BoardTrace.exe is currently unsigned. The target PC rejected it under application control.",
        "Please review CodeIntegrity/AppLocker block events from that PC and approve this exact release",
        "under your organization policy, or provide a code-signing route trusted by the target PC.",
        "The program listens on 127.0.0.1:5000 by default and writes application data beside the executable.",
        "No existing database or attachments are included in the ZIP.", "",
        "SHA256  RELATIVE_PATH",
    ]
    lines.extend(f"{digest}  {name}" for name, digest in hashes)
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")
    print(f"{MANIFEST} ({len(hashes)} binaries)")


if __name__ == "__main__":
    main()
