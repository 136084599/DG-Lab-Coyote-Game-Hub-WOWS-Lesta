"""Incremental byte tailer and pure log parser; never replays an old battle."""
from dataclasses import dataclass
import logging
import math
import os
from pathlib import Path
import re

LOG = logging.getLogger(__name__)
SNAPSHOT = re.compile(r'^[^,]+\((?P<max>[0-9.]+)\),(?P<hp>[0-9.]+),isDied:(?P<dead>True|False),Burning:(?P<fire>True|False),Flooding:(?P<flood>True|False),Kills:(?P<kills>\d+),Achievements:(?P<achievements>\d+)\s*$')
DAMAGE = re.compile(r'damage:\s*([0-9]+(?:\.[0-9]+)?)')


@dataclass(frozen=True)
class Snapshot:
    maximum: float
    health: float
    dead: bool
    burning: bool
    flooding: bool
    kills: int
    achievements: int


def parse(line):
    if line.startswith('BattleStart,') or line == 'BattleEnd':
        return ('reset', 0)
    match = SNAPSHOT.fullmatch(line)
    if match:
        m = match.groupdict()
        maximum, health = float(m['max']), float(m['hp'])
        if not math.isfinite(maximum) or not math.isfinite(health) or not 0 <= health <= maximum or maximum <= 0:
            raise ValueError('无效的血量快照')
        return Snapshot(maximum, health, m['dead'] == 'True', m['fire'] == 'True',
                        m['flood'] == 'True', int(m['kills']), int(m['achievements']))
    if any(tag in line for tag in ('Burning:', 'Flooding:', 'Kills:', 'Achievements:')):
        raise ValueError('不完整或格式不匹配的血量快照')
    if line.startswith('MaxHealth,'):
        maximum = float(line.split(',')[1])
        if not math.isfinite(maximum) or maximum <= 0:
            raise ValueError('无效的最大血量')
        return ('max', maximum)
    if 'isDied:True' in line:
        return ('death', 0)
    if 'damage:' in line:
        damage = sum(float(n) for n in DAMAGE.findall(line))
        if not math.isfinite(damage):
            raise ValueError('无效的伤害')
        return ('damage', damage)
    if ',isDied:' in line:
        raise ValueError('不完整或格式不匹配的快照')
    return None


class LogTail:
    """Keep a partial line until newline; detect truncate, replace, and rewrites.

    A short prefix and the last consumed bytes cover same-size rewrites without
    rereading the whole log. Identical rewrites cannot be distinguished without
    a battle ID in the producer; the recorder's timestamp normally disambiguates.
    """
    def __init__(self, path):
        self.path = Path(path)
        self.position = 0
        self.partial = b''
        self.identity = None
        self.prefix = b''
        self.anchor = b''
        self.started = False
        self.exists = False

    def read(self):
        try:
            f = self.path.open('rb')
        except FileNotFoundError:
            reset = self.exists
            self.exists = False
            self.identity = None
            self.position = 0
            self.partial = b''
            self.prefix = self.anchor = b''
            return reset, False, []
        with f:
            st = os.fstat(f.fileno())
            identity = (st.st_dev, st.st_ino)
            prefix = f.read(len(self.prefix))
            f.seek(max(0, self.position - len(self.anchor)))
            anchor = f.read(len(self.anchor))
            reset = self.identity is not None and (identity != self.identity or st.st_size < self.position or prefix != self.prefix or anchor != self.anchor)
            baseline = not self.started
            if reset:
                self.position = 0
                self.partial = b''
            if baseline:
                # A bounded tail is enough to baseline cumulative counters.
                self.position = max(0, st.st_size - 65536)
                f.seek(self.position)
                if self.position:
                    f.readline()
                    self.position = f.tell()
            f.seek(self.position)
            chunk = f.read(262144)
            self.position = f.tell()
            lines = (self.partial + chunk).split(b'\n')
            self.partial = lines.pop()
            if len(self.partial) > 65536:
                LOG.warning('丢弃超过 64 KiB 的未结束日志行')
                self.partial = b''
            f.seek(0)
            self.prefix = f.read(min(128, self.position))
            f.seek(max(0, self.position - 128))
            self.anchor = f.read(min(128, self.position))
            self.identity = identity
            self.exists = True
            self.started = True
            return reset, baseline, [line.decode('utf-8', errors='replace').strip() for line in lines]


class BattleParser:
    def __init__(self, engine):
        self.engine = engine
        self.reset()
        self.lines = 0
        self.errors = 0

    def reset(self):
        self.previous = None
        self.maximum = None
        self.dead = False
        self.last_kill = float('-inf')
        self.streak = 0

    def feed(self, line, now, baseline=False):
        self.lines += 1
        try:
            item = parse(line)
        except (ValueError, OverflowError) as e:
            self.errors += 1
            LOG.warning('跳过无效日志行: %s', e)
            return
        if item is None:
            return
        if not isinstance(item, Snapshot):
            kind, value = item
            if kind == 'reset':
                self.reset()
                self.engine.reset(now)
            elif kind == 'max':
                self.maximum = value
            elif not baseline and kind == 'death' and not self.dead:
                self.dead = True
                self.engine.death(now)
            elif not baseline and kind == 'damage' and self.maximum and not self.dead:
                self.engine.damage(value, self.maximum, now)
            return
        previous = self.previous
        if previous and (item.maximum != previous.maximum or item.kills < previous.kills or item.achievements < previous.achievements or (previous.dead and not item.dead)):
            self.reset()
            self.engine.reset(now)
            previous = None
        self.previous = item
        self.maximum = item.maximum
        if baseline or previous is None:
            self.dead = item.dead
            # Establish state only; never turn startup history into rewards/hits.
            return
        if self.dead:
            return
        kills = item.kills - previous.kills
        if kills > 0:
            window = self.engine.cfg['rules']['streak']['window']
            self.streak = self.streak + kills if now - self.last_kill <= window else kills
            self.last_kill = now
            self.engine.reward('kill', kills, now)
            if self.streak >= self.engine.cfg['rules']['streak']['minConsecutive']:
                self.engine.reward('streak', 1, now)
        self.engine.reward('achievement', item.achievements - previous.achievements, now)
        # Synchronize status on each fresh snapshot, including after a baseline.
        self.engine.status('burning', item.burning, now)
        self.engine.status('flooding', item.flooding, now)
        if item.dead:
            self.dead = True
            self.engine.death(now)
        elif item.health < previous.health:
            self.engine.damage(previous.health - item.health, item.maximum, now)
