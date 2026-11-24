"""Installation diagnostics and explicit, backed-up recorder installation."""
import csv
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .config import ROOT
from .discovery import EXECUTABLES, inspect_game


def running_games():
    if os.name != 'nt':
        return []
    result = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True,
        text=True, errors='replace', timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('无法检查游戏是否运行，请退出游戏并重试')
    expected = {name.lower() for name in EXECUTABLES}
    return [row[0] for row in csv.reader(io.StringIO(result.stdout)) if row and row[0].lower() in expected]


def install_recorder(game_path, sample_sec=0.2):
    from .config import number
    number(sample_sec, '游戏采集间隔', 0.05, 2)
    info = inspect_game(game_path)
    if not info['valid']:
        raise ValueError(info['message'])
    if running_games():
        raise ValueError('游戏仍在运行。请先退出游戏，再安装或更新采集插件。')
    target = Path(info['mod_path'])
    loader = Path(info['loader_path'])
    source = ROOT / 'mods/BattleRecorder/Main.py'
    content = source.read_text('utf8').replace('DELAY = 0.2', f'DELAY = {sample_sec!r}', 1).encode('utf8')
    # This empty marker enables ModsAPI. Never overwrite an existing loader.
    loader.parent.mkdir(parents=True, exist_ok=True)
    loader_created = False
    try:
        with loader.open('xb'):
            pass
        loader_created = True
    except FileExistsError:
        pass
    if target.exists() and target.read_bytes() == content:
        return {'message': '当前采集插件已就绪' + ('；已补齐 ModsAPI 加载标记' if loader_created else '，无需重复安装'),
                'path': str(target), 'backup': None, 'loader_created': loader_created}
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists():
        backup = target.with_name(f'Main.py.{time.time_ns()}.bak')
        shutil.copy2(target, backup)
    fd, temporary = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'message': '采集插件已安装。请启动游戏，在训练房确认日志更新后再启用联动。',
            'path': str(target), 'backup': str(backup) if backup else None,
            'loader_created': loader_created, 'loader_path': str(loader)}
