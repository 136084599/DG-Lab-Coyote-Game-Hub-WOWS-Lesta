"""One entry point; reuse an existing Hub and stop only a child we own."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser
from urllib.parse import urlparse
from urllib.request import urlopen

from wows_bridge.config import ROOT, HUB_DIR, load


def ready(url):
    try:
        with urlopen(url.rstrip('/') + '/api/server_info', timeout=0.3) as response:
            return json.load(response).get('status') == 1
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.yaml')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--check-config', action='store_true')
    args, _ = parser.parse_known_args()
    child, log = None, None
    try:
        cfg = load(args.config)
        if not args.check_config:
            console_url = f'http://127.0.0.1:{cfg["web_port"]}'
            try:
                with urlopen(console_url + '/api/status', timeout=.3) as response:
                    status = json.load(response)
                if 'desired_strength' in status and 'dry_run' in status:
                    if status['dry_run'] != args.dry_run:
                        raise RuntimeError('控制台已在另一种模式运行，请先退出已有实例再切换模拟/设备模式')
                    print('控制台已经运行，已打开现有页面。')
                    webbrowser.open(console_url)
                    return 0
            except (OSError, ValueError):
                pass
        try:
            url = cfg['hub']['api_url']
            if not args.dry_run and not args.check_config and not ready(url):
                target = urlparse(url)
                if target.hostname not in ('127.0.0.1', 'localhost', '::1'):
                    raise RuntimeError('远端 Hub 不可达，请先启动远端服务')
                from wows_bridge.config import read_yaml
                hub_cfg = read_yaml(HUB_DIR / 'config.yaml')
                if (target.port or 80) != hub_cfg.get('port', 8920):
                    raise RuntimeError('本机 Hub 端口与 hub.api_url 不一致，请先修改配置')
                node = HUB_DIR / 'bin' / 'node.exe'
                if not node.exists():
                    raise RuntimeError(f'找不到内置 Node：{node}')
                log_dir = ROOT / 'logs'
                log_dir.mkdir(exist_ok=True)
                log = (log_dir / 'hub.log').open('ab')
                child = subprocess.Popen([str(node), 'server/index.js'], cwd=HUB_DIR,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                deadline = time.monotonic() + 20
                while not ready(url):
                    if child.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('Hub 启动失败或超时，详情见 logs/hub.log')
                    time.sleep(0.2)
                print('Hub 已就绪。')
        except (RuntimeError, ValueError, OSError) as exc:
            print(f'设备服务暂不可用：{exc}。继续打开控制台，可检查路径、参数和连接设置。', file=sys.stderr)
        from wows_bridge.app import main as run_bridge
        run_bridge()
    except (RuntimeError, ValueError, OSError) as e:
        print(f'启动失败：{e}', file=sys.stderr)
        return 1
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if log:
            log.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
