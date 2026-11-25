"""Build a clean Windows x64 bridge package from recorded upstream inputs."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
import urllib.request
import zipfile

PYTHON = (
    "https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-amd64.zip",
    "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297",
    "python-3.13.16-embed-amd64.zip",
)
HUB = (
    "https://github.com/hyperzlib/DG-Lab-Coyote-Game-Hub/releases/download/v2.0.0/coyote-game-hub-windows-amd64-dist.zip",
    "28a0f1440cbe1cdd4dfba4f1cb68ae6efea59ce82e51b263107be31038e0fef4",
    "hub-win.zip",
)
NODE = (
    "https://nodejs.org/dist/v22.23.5/node-v22.23.5-win-x64.zip",
    "4a191082e9706866830379d577d2cc8a50c776fcd9436a8d061b063ed0d9a0e3",
    "node-v22.23.5-win-x64.zip",
)
BRIDGE_ITEMS = (
    "config.example.yaml", "launcher.py", "main.py", "start.bat",
    "README.md", "CHANGELOG.md", "uv.lock", "pyproject.toml",
    "demo", "hub-overlay", "mods", "tests", "tools", "web", "wows_bridge",
)
HUB_FILES = {
    "config.example.yaml", "version.json", "package.json",
    "data/pulse.json5", "server/index.js", "server/package.json", "server/licenses.txt",
}
PUBLISHABLE = "Lesta-Coyote-Windows-x64-Portable.zip"
HUB_DIRECTORY = Path("coyote-game-hub-windows-amd64-dist") / "coyote-game-hub"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(item, cache):
    url, expected, name = item
    path = cache / name
    if not path.exists():
        incoming = path.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=85) as response, incoming.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if sha256(incoming) != expected:
            raise ValueError(f"SHA-256 mismatch for {name}")
        incoming.replace(path)
    if sha256(path) != expected:
        raise ValueError(f"SHA-256 mismatch for {name}")
    return path


def copy_member(archive, member, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member) as source, destination.open("wb") as output:
        shutil.copyfileobj(source, output)


def install_python(archive_path, bridge, work):
    runtime = bridge / "python_env"
    runtime.mkdir()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if not member.is_dir() and len(PurePosixPath(member.filename).parts) == 1:
                copy_member(archive, member, runtime / member.filename)
    path_file = runtime / "python313._pth"
    path_file.write_text("python313.zip\n.\n..\nLib/site-packages\nimport site\n", encoding="ascii")
    lock = tomllib.loads((bridge / "uv.lock").read_text(encoding="utf-8"))
    requirements = work / "wheel-requirements.txt"
    lines = []
    for package in lock["package"]:
        if "registry" not in package["source"]:
            continue
        hashes = sorted({wheel["hash"] for wheel in package["wheels"]})
        if not hashes:
            raise ValueError(f"Missing wheel hashes for {package['name']}")
        pin = f"{package['name']}=={package['version']}"
        lines.append(f"{pin} " + " ".join(f"--hash={digest}" for digest in hashes))
    requirements.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
         "--no-input", "--no-deps", "--no-compile", "--require-hashes",
         "--index-url", "https://pypi.org/simple", "--only-binary=:all:",
         "--platform", "win_amd64", "--python-version", "3.13", "--implementation", "cp",
         "--target", str(runtime / "Lib" / "site-packages"), "-r", str(requirements)],
        check=True,
    )


def install_hub(archive_path, node_path, bridge):
    hub = bridge / HUB_DIRECTORY
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            relative = PurePosixPath(name)
            if name.endswith("/") or relative.parts[0] != "coyote-game-hub":
                continue
            path = PurePosixPath(*relative.parts[1:])
            if ".." in path.parts:
                raise ValueError("Unsafe Hub ZIP member")
            if path.as_posix() in HUB_FILES or path.parts[0] == "public":
                copy_member(archive, name, hub.joinpath(*path.parts))
    with zipfile.ZipFile(node_path) as archive:
        for name in ("node.exe", "LICENSE"):
            member = next(name_ for name_ in archive.namelist()
                          if PurePosixPath(name_).parts == ("node-v22.23.5-win-x64", name))
            copy_member(archive, member, hub / "bin" / name)
    (hub / "config.yaml").write_text(
        'port: 8920\nhost: "127.0.0.1"\npulseConfigPath: "pulse.yaml"\nopenBrowser: false\n'
        "allowBroadcastToClients: true\n", encoding="utf-8"
    )
    subprocess.run(
        [str(bridge / "python_env" / "python.exe"), str(bridge / "tools" / "apply_hub_150_overlay.py"),
         str(hub), "--apply"], cwd=bridge, check=True,
    )
    # The unmodified upstream bundle remains obtainable by its verified digest.
    (hub / "server" / "index.js.lesta-backup").unlink()


def build(source, packaging, license_path, cache, output):
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="lesta-portable-") as tmp:
        work = Path(tmp)
        bridge = work / "Lesta-Coyote"
        bridge.mkdir()
        for name in BRIDGE_ITEMS:
            item = source / name
            if item.is_dir():
                shutil.copytree(item, bridge / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copyfile(item, bridge / name)
        for name in ("Start.cmd", "Start-Demo.cmd", "PORTABLE-README.md"):
            shutil.copyfile(packaging / name, bridge / name)
        shutil.copyfile(license_path, bridge / "LICENSE-Hub.txt")
        install_python(download(PYTHON, cache), bridge, work)
        install_hub(download(HUB, cache), download(NODE, cache), bridge)
        origins = {name: {"url": item[0], "sha256": item[1]} for name, item in
                   (("python", PYTHON), ("coyote_game_hub", HUB), ("node", NODE))}
        (bridge / "upstream-components.json").write_text(json.dumps(origins, indent=2) + "\n", encoding="utf-8")
        artifact = output / PUBLISHABLE
        with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file in sorted(bridge.rglob("*")):
                relative = file.relative_to(bridge)
                generated_scripts = relative.parts[:4] == ("python_env", "Lib", "site-packages", "bin")
                if file.is_file() and file.suffix != ".pyc" and not generated_scripts:
                    archive.write(file, file.relative_to(work).as_posix())
        (output / "SHA256SUMS.txt").write_text(f"{sha256(artifact)}  {artifact.name}\n", encoding="ascii")
        print(f"Built {artifact.name} ({artifact.stat().st_size} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--license", required=True, type=Path)
    args = parser.parse_args()
    build(args.source.resolve(), Path(__file__).resolve().parent, args.license.resolve(),
          args.cache.resolve(), args.output.resolve())
