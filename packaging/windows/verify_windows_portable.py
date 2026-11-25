"""Verify the portable archive on Windows without a game client or device."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from build_windows_portable import HUB_DIRECTORY, sha256

HUB_ENTRY_SHA256 = "4edbd7738e6406cef1d27793f86c3b01f9262768ad4f103d009bbe675e561e52"


def free_ports():
    with socket.socket() as first, socket.socket() as second:
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        return first.getsockname()[1], second.getsockname()[1]


def response(opener, url, as_json=False):
    with opener.open(url, timeout=2) as stream:
        return json.load(stream) if as_json else stream.read()


def wait_for(opener, url, child):
    for _ in range(100):
        if child.poll() is not None:
            break
        try:
            return response(opener, url, True)
        except (OSError, ValueError):
            time.sleep(0.3)
    raise RuntimeError(f"Startup check failed: {url}")


def check_startup(bridge, directory, demo):
    web, hub = free_ports()
    example = (bridge / "config.example.yaml").read_text(encoding="utf-8")
    config = bridge / ("config.offline.yaml" if demo else "config.yaml")
    config.write_text(
        example.replace("127.0.0.1:8920", f"127.0.0.1:{hub}") +
        f"\nweb_port: {web}\nopen_browser: false\n", encoding="utf-8",
    )
    hub_config = bridge / HUB_DIRECTORY / "config.yaml"
    hub_config.write_text(
        'host: "127.0.0.1"\nopenBrowser: false\nallowBroadcastToClients: true\n'
        f"port: {hub}\npulseConfigPath: pulse.yaml\n", encoding="utf-8",
    )
    bridge_url = f"http://127.0.0.1:{web}"
    hub_url = f"http://127.0.0.1:{hub}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    log = directory / ("demo.log" if demo else "live.log")
    command = "Start-Demo.cmd" if demo else "Start.cmd"
    with log.open("wb") as output:
        child = subprocess.Popen(
            [os.environ["ComSpec"], "/d", "/c", command, "--no-browser"], cwd=bridge,
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            status = wait_for(opener, bridge_url + "/api/status", child)
            assert status["dry_run"] is demo
            assert status["desired_strength"] == 0
            assert "调参实验室".encode() in response(opener, bridge_url + "/")
            if demo:
                with socket.socket() as probe:
                    assert probe.connect_ex(("127.0.0.1", hub)) != 0
            else:
                assert wait_for(opener, hub_url + "/api/server_info", child)["status"] == 1
                assert response(opener, hub_url + "/api/v2/game/all/pulse_list", True)["status"] == 1
                assert response(opener, hub_url + "/pulse-import-worker.js")
        except Exception:
            output.flush()
            print(log.read_text(encoding="utf-8", errors="replace")[-2800:])
            hub_log = bridge / "logs" / "hub.log"
            if hub_log.exists():
                print(hub_log.read_text(encoding="utf-8", errors="replace")[-2200:])
            raise
        finally:
            if child.poll() is None:
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            child.wait(timeout=8)


def check_installation(bridge, directory):
    game = directory / "Mock Game"
    build = game / "bin" / "1111111"
    build.mkdir(parents=True)
    (game / "Korabli.exe").touch()
    fixture = """
from pathlib import Path
import sys
from wows_bridge.setup import install_recorder

game = sys.argv[1]
result = install_recorder(game)
target = Path(result['path'])
loader = Path(result['loader_path'])
assert loader.name == 'PnFModsLoader.py'
assert loader.read_bytes() == b''
assert target.read_text(encoding='utf-8') == Path('mods/BattleRecorder/Main.py').read_text(encoding='utf-8')
target.write_bytes(b'old recorder fixture')
updated = install_recorder(game)
assert Path(updated['backup']).read_bytes() == b'old recorder fixture'
assert not updated['loader_created']
assert install_recorder(game)['backup'] is None
"""
    subprocess.run([str(bridge / "python_env" / "python.exe"), "-c", fixture, str(game)],
                   cwd=bridge, check=True, timeout=25)


def verify(artifact, workspace):
    digest = artifact.with_name("SHA256SUMS.txt").read_text(encoding="ascii").split()[0]
    assert sha256(artifact) == digest
    with tempfile.TemporaryDirectory(prefix="lesta-verify-", dir=workspace) as tmp:
        directory = Path(tmp)
        with zipfile.ZipFile(artifact) as archive:
            assert archive.testzip() is None
            for entry in archive.namelist():
                assert entry.startswith("Lesta-Coyote/")
                assert "/.env" not in entry and "/logs/" not in entry and "/game-config/" not in entry
                assert "/site-packages/bin/" not in entry
                assert not entry.endswith(("config.offline.yaml", "credentials.json", ".pyc"))
            archive.extractall(directory)
        bridge = directory / "Lesta-Coyote"
        assert not (bridge / "config.yaml").exists()
        assert sha256(bridge / HUB_DIRECTORY / "server" / "index.js") == HUB_ENTRY_SHA256
        check_startup(bridge, directory, demo=True)
        check_startup(bridge, directory, demo=False)
        check_installation(bridge, directory)
        subprocess.run([str(bridge / "python_env" / "python.exe"), "-m", "unittest", "discover", "-s", "tests"],
                       cwd=bridge, check=True, timeout=145)
    print("Portable demo, bundled Hub, backed-up mod installation, and bridge tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    verify(args.artifact.resolve(), args.artifact.resolve().parent)
