"""Explicit installer; shares checks/backups with the control panel."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wows_bridge.config import ROOT, load
from wows_bridge.setup import install_recorder


def main():
    parser = argparse.ArgumentParser(description='安装 BattleRecorder；请先退出游戏')
    parser.add_argument('--game-path', type=Path)
    args = parser.parse_args()
    cfg = load(ROOT / 'config.yaml')
    path = str(args.game_path) if args.game_path else cfg['wows_path']
    try:
        result = install_recorder(path, cfg['recorder']['sample_sec'])
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')
    print(result['message'])
    print(result['path'])
    if result['backup']:
        print('原文件备份：', result['backup'])


if __name__ == '__main__':
    main()
