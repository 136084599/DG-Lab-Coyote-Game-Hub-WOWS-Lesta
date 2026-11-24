"""Reuse the bundled Hub's viewer; never create/bind a session to find an ID."""
from pathlib import Path
import re
from urllib.parse import parse_qs, urlencode, urlparse

THEMES = [
    {'id': 'circle', 'name': '经典圆盘', 'route': '', 'width': 420, 'height': 420},
    {'id': 'bar', 'name': '横向胶囊', 'route': 'bar1', 'width': 600, 'height': 160},
    {'id': 'hearts', 'name': '像素心心血条', 'route': 'health-bar1', 'width': 600, 'height': 160},
    {'id': 'battery', 'name': '拟物电池', 'route': 'battery1', 'width': 400, 'height': 500},
]


def browser_url(api_url):
    parsed = urlparse(api_url)
    if parsed.hostname == 'localhost' and parsed.username is None:
        parsed = parsed._replace(netloc='127.0.0.1' + (f':{parsed.port}' if parsed.port else ''))
    return parsed.geturl().rstrip('/')


def client_id(value):
    if not isinstance(value, str):
        raise ValueError('请输入会话 ID 或原版 OBS 链接')
    value = value.strip()
    if value.startswith(('http://', 'https://')):
        value = parse_qs(urlparse(value).query).get('clientId', [''])[0]
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', value) or value.lower() in ('all', 'all.channelb'):
        raise ValueError('OBS 原版皮肤需要具体会话 ID，不能使用 all；也可粘贴原版“添加到OBS”生成的完整链接')
    return value


def viewer_link(base, target, theme='circle'):
    target = client_id(target)
    chosen = next((entry for entry in THEMES if entry['id'] == theme), None)
    if chosen is None:
        raise ValueError('未知显示皮肤')
    suffix = '?darkMode=true' if theme == 'circle' else ''
    return dict(chosen, url=f'{browser_url(base)}/viewer.html?{urlencode({"clientId": target})}#/{chosen["route"]}{suffix}')


def saved_sessions(hub_dir):
    sessions = []
    directory = Path(hub_dir) / 'data/game-config'
    if directory.is_dir():
        for file in sorted(directory.glob('*.main-game.json'))[:100]:
            try:
                sessions.append(client_id(file.name.removesuffix('.main-game.json')))
            except ValueError:
                continue
    return sessions
