"""Deterministic, hardware-free rule preview using the production engine."""
import random

from .config import number, validate
from .engine import RuleEngine


def simulate(config, events, duration=10):
    cfg = validate(config)
    number(duration, '预览秒数', 1, 60)
    if not isinstance(events, list) or len(events) > 200:
        raise ValueError('最多预览 200 个事件')
    ordered = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('事件必须是对象')
        number(event.get('time'), '事件时刻', 0, duration)
        kind = event.get('kind')
        if kind not in ('damage', 'kill', 'achievement', 'streak', 'burning', 'flooding', 'death', 'reset'):
            raise ValueError('未知预览事件')
        if kind == 'damage':
            number(event.get('percent'), '损血百分比', 0, 100)
        if kind in ('burning', 'flooding') and not isinstance(event.get('active'), bool):
            raise ValueError('状态 active 须为布尔值')
        ordered.append(event)
    ordered.sort(key=lambda e: e['time'])
    engine = RuleEngine(cfg, random.Random(42))
    index, samples = 0, []
    for tick in range(int(duration * 50) + 1):
        now = tick / 50
        while index < len(ordered) and ordered[index]['time'] <= now:
            event = ordered[index]
            kind = event['kind']
            if kind == 'damage':
                engine.damage(event['percent'], 100, now)
            elif kind in ('burning', 'flooding'):
                engine.status(kind, event['active'], now)
            elif kind == 'death':
                engine.death(now)
            elif kind == 'reset':
                engine.reset(now)
            else:
                engine.reward(kind, 1, now)
            index += 1
        strength, pulse = engine.desired(now)
        samples.append({'time': now, 'strength': strength, 'base': round(engine.base, 3), 'pulse': pulse})
    return {'samples': samples, 'peak': max(p['strength'] for p in samples),
            'duration': duration, 'limit': cfg['shock']['maxStrength'], 'seed': 42, 'config': cfg}
