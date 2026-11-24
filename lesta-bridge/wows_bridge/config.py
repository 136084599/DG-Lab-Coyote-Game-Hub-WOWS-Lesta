"""Validated configuration, old YAML migration, and atomic persistence."""
from copy import deepcopy
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
HUB_DIR = ROOT / 'coyote-game-hub-windows-amd64-dist' / 'coyote-game-hub'
DEFAULTS = {
    'wows_path': '', 'log_path': '', 'window_sec': 0.3, 'poll_sec': 0.05,
    'web_port': 8080, 'open_browser': True,
    'shock': {'usingApi': ['dglab'], 'addStrengthWhenHitInThisRound': 0.12,
              'minBaseStrength': 0, 'maxStrength': 100, 'defaultPulseId': None,
              'minDamagePercent': 0, 'damageScale': 1, 'retrigger': 'replace',
              'baseRecovery': {'enabled': False, 'delay': 10, 'rate': 1}},
    'output': {'tick_sec': 0.02, 'heartbeat_sec': 2, 'retry_sec': 1},
    'recorder': {'sample_sec': 0.2},
    'rules': {
        'kill': {'enabled': True, 'strengthDelta': -1, 'pulseId': None, 'pulseDuration': 4},
        'achievement': {'enabled': True, 'strengthDelta': -2, 'pulseId': None, 'pulseDuration': 4},
        'streak': {'enabled': True, 'strengthDelta': -1, 'pulseId': None,
                   'pulseDuration': 4, 'minConsecutive': 2, 'window': 8},
        'burning': {'enabled': True, 'strengthDelta': 16, 'pulseId': None},
        'flooding': {'enabled': True, 'strengthDelta': 18, 'pulseId': None},
        'death': {'enabled': True, 'strengthDelta': 60, 'pulseId': None,
                  'pulseDuration': 4, 'duration': 9},
    },
    'hub': {'api_url': 'http://127.0.0.1:8920/', 'toAllDevices': True,
            'client_id': '', 'timeout': 1.0,
            'Segment': [[0, 10], [1, 25], [3, 60], [5, 85], [8, 105],
                        [10, 108], [15, 125], [20, 132], [30, 138], [40, 142],
                        [50, 145], [60, 147], [75, 148.5], [90, 149], [100, 149], [101, 150]],
            'interpolation': 'step', 'randomize_strength_range': [-3, 7],
            'hit_duration': 0.2,
            'decay': {'enabled': True, 'mode': 'step', 'hold_sec': 0,
                      'interval': 0.3, 'factor': 0.4, 'min_strength': 0,
                      'half_life': 0.3, 'linear_rate': 50, 'max_duration': 30}},
}


def merge(base, patch):
    result = deepcopy(base)
    for key, value in patch.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} 必须是有限数值')
    if not low <= value <= high or (integer and value != int(value)):
        raise ValueError(f'{name} 必须在 {low}～{high} 之间' + ('，且为整数' if integer else ''))


def pulse(value, name):
    if value is None:
        return
    values = value if isinstance(value, list) else [value]
    if not values or any(not isinstance(v, str) or not v.strip() or len(v) > 128 for v in values):
        raise ValueError(f'{name} 必须是波形 ID、非空 ID 列表或 null')


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError('配置必须为对象')
    cfg = merge(DEFAULTS, raw)
    for key in ('shock', 'rules', 'hub', 'output', 'recorder'):
        if not isinstance(cfg[key], dict):
            raise ValueError(f'{key} 必须为对象')
    for key in ('wows_path', 'log_path'):
        if not isinstance(cfg[key], str):
            raise ValueError(f'{key} 必须为路径字符串')
    number(cfg['window_sec'], 'window_sec', 0.01, 5)
    number(cfg['poll_sec'], 'poll_sec', 0.01, 1)
    number(cfg['web_port'], 'web_port', 1024, 65535, True)
    cfg['web_port'] = int(cfg['web_port'])
    if not isinstance(cfg['open_browser'], bool):
        raise ValueError('open_browser 必须是布尔值')
    shock = cfg['shock']
    number(shock['maxStrength'], 'maxStrength', 0, 200, True)
    number(shock['minBaseStrength'], 'minBaseStrength', 0, shock['maxStrength'])
    number(shock['addStrengthWhenHitInThisRound'], '受击基数增量', 0, 200)
    number(shock['minDamagePercent'], '最小触发损血百分比', 0, 100)
    number(shock['damageScale'], '伤害曲线倍率', 0, 10)
    if shock['retrigger'] not in ('replace', 'max', 'add'):
        raise ValueError('再次受击模式必须是 replace、max 或 add')
    recovery = shock['baseRecovery']
    if not isinstance(recovery, dict) or not isinstance(recovery.get('enabled'), bool):
        raise ValueError('baseRecovery.enabled 必须是布尔值')
    number(recovery['delay'], '基础值恢复等待', 0, 600)
    number(recovery['rate'], '基础值每秒恢复点数', 0.01, 200)
    number(cfg['output']['tick_sec'], '输出检查间隔', 0.01, 0.2)
    number(cfg['output']['heartbeat_sec'], '状态重申间隔', 0.2, 30)
    number(cfg['output']['retry_sec'], '断线重试间隔', 0.1, 30)
    number(cfg['recorder']['sample_sec'], '游戏采集间隔', 0.05, 2)
    if not isinstance(shock['usingApi'], list) or [str(n).lower() for n in shock['usingApi']] != ['dglab']:
        raise ValueError('当前支持 usingApi: [dglab]；离线测试请使用 --dry-run')
    shock['usingApi'] = ['dglab']
    pulse(shock['defaultPulseId'], '默认波形')
    for name in DEFAULTS['rules']:
        rule = cfg['rules'][name]
        if not isinstance(rule, dict) or not isinstance(rule.get('enabled'), bool):
            raise ValueError(f'{name}.enabled 必须是布尔值')
        number(rule['strengthDelta'], f'{name}.strengthDelta', -200, 200)
        pulse(rule['pulseId'], f'{name}.pulseId')
        if 'pulseDuration' in rule:
            number(rule['pulseDuration'], f'{name}.pulseDuration', 0.01, 60)
        if rule['enabled'] and rule['pulseId'] and not shock['defaultPulseId']:
            raise ValueError('启用事件波形前请设置默认波形，以便事件结束后恢复')
    number(cfg['rules']['death']['duration'], '死亡持续秒数', 0.01, 30)
    number(cfg['rules']['streak']['window'], '连杀间隔', 0.1, 300)
    number(cfg['rules']['streak']['minConsecutive'], '连杀门槛', 2, 100, True)
    cfg['rules']['streak']['minConsecutive'] = int(cfg['rules']['streak']['minConsecutive'])
    hub = cfg['hub']
    if not isinstance(hub['api_url'], str):
        raise ValueError('hub.api_url 必须是 URL')
    url = urlparse(hub['api_url'])
    if url.scheme not in ('http', 'https') or not url.hostname or url.query or url.fragment:
        raise ValueError('hub.api_url 必须是 http(s) 服务地址')
    if not isinstance(hub['toAllDevices'], bool) or not isinstance(hub['client_id'], str):
        raise ValueError('toAllDevices / client_id 类型错误')
    if not hub['toAllDevices'] and not hub['client_id'].strip():
        raise ValueError('单设备模式需填写 Hub 已连接游戏的 client_id')
    if hub['client_id'] and any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._' for c in hub['client_id']):
        raise ValueError('client_id 含有无效字符')
    number(hub['timeout'], 'Hub 请求超时', 0.1, 5)
    number(hub['hit_duration'], '单次受击持续时间', 0.01, 10)
    if hub['interpolation'] not in ('step', 'linear'):
        raise ValueError('interpolation 必须是 step 或 linear')
    segments = hub['Segment']
    if not isinstance(segments, list) or not segments:
        raise ValueError('Segment 不能为空')
    previous = -1
    for row in segments:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError('每个 Segment 项必须是 [伤害百分比, 强度]')
        number(row[0], '伤害百分比', 0, 10000)
        number(row[1], '分段强度', 0, 200)
        if row[0] <= previous:
            raise ValueError('Segment 阈值必须严格递增，不能重复')
        previous = row[0]
    r = hub['randomize_strength_range']
    if not isinstance(r, list) or len(r) != 2:
        raise ValueError('随机范围必须包含两个整数')
    number(r[0], '随机下限', -200, 200, True)
    number(r[1], '随机上限', r[0], 200, True)
    hub['randomize_strength_range'] = [int(v) for v in r]
    decay = hub['decay']
    if not isinstance(decay, dict) or not isinstance(decay.get('enabled'), bool):
        raise ValueError('decay.enabled 必须是布尔值')
    number(decay['interval'], '衰减间隔', 0.01, 10)
    number(decay['factor'], '衰减保留系数', 0.001, 0.999)
    number(decay['min_strength'], '衰减下限', 0, shock['maxStrength'])
    if decay['mode'] not in ('step', 'half_life', 'linear'):
        raise ValueError('衰减模式必须是 step、half_life 或 linear')
    number(decay['hold_sec'], '受击峰值保持时间', 0, 10)
    number(decay['half_life'], '衰减半衰期', 0.01, 30)
    number(decay['linear_rate'], '每秒衰减点数', 0.01, 1000)
    number(decay['max_duration'], '受击效果最长时间', 0.01, 60)
    if decay['hold_sec'] >= decay['max_duration']:
        raise ValueError('峰值保持时间须小于受击效果最长时间')
    return cfg


def read_yaml(path):
    with Path(path).open(encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def load(path):
    raw = read_yaml(path) if Path(path).exists() else {}
    if not isinstance(raw, dict):
        raise ValueError('配置必须为对象')
    legacy = ROOT / 'apis' / 'dglab' / 'config.yaml'
    if 'hub' not in raw and legacy.exists():
        raw['hub'] = read_yaml(legacy)
    return validate(raw)


def pulse_ids(cfg):
    values = [cfg['shock']['defaultPulseId']] + [rule.get('pulseId') for rule in cfg['rules'].values() if isinstance(rule, dict)]
    return {pid for value in values for pid in (value if isinstance(value, list) else [value]) if pid}


def save(path, cfg):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def log_path(cfg):
    if cfg['log_path']:
        path = Path(cfg['log_path'])
        return path if path.is_absolute() else ROOT / path
    game = Path(cfg['wows_path'])
    from .game_paths import active_build
    build, _ = active_build(game)
    if build:
        return build / 'res_mods/PnFMods/BattleRecorder/damage_log.txt'
    return game / 'damage_log.txt' if cfg['wows_path'] else ROOT / 'damage_log.txt'
