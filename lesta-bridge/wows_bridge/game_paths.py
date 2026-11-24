"""Choose the installed client build, avoiding pre-download directories."""
from pathlib import Path
import xml.etree.ElementTree as ET


def active_build(game):
    game = Path(game)
    builds = game / 'bin'
    if not builds.is_dir():
        return None, '未找到 bin 目录'
    metadata = game / 'game_info.xml'
    if metadata.is_file():
        try:
            if metadata.stat().st_size <= 1024 * 1024:
                tree = ET.parse(metadata)
                version = tree.find(".//part_versions/version[@name='client']")
                if version is not None:
                    installed = version.get('installed', '').split('.')[-1]
                    if installed.isdigit() and (builds / installed).is_dir():
                        return builds / installed, '游戏中心已安装版本'
                    if installed.isdigit() and installed != '0':
                        return None, '游戏中心记录的已安装版本目录缺失，请先完成更新或修复'
        except (ET.ParseError, OSError):
            pass
    versions = [p for p in builds.iterdir() if p.is_dir() and p.name.isdigit()]
    return (max(versions, key=lambda p: int(p.name)), '数字目录回退检测') if versions else (None, '没有已安装的版本目录')
