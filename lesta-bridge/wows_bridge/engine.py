"""Pure rule state machine. One output worker samples it; no per-hit tasks."""
import logging
import math
import random

LOG = logging.getLogger(__name__)


def mapped_strength(percentage, hub):
    if percentage <= 0:
        return 0
    rows = hub['Segment']
    for i, (threshold, strength) in enumerate(rows):
        if percentage < threshold:
            if i == 0:
                return strength
            x, y = rows[i - 1]
            if hub['interpolation'] == 'linear':
                return y + (strength - y) * (percentage - x) / (threshold - x)
            return y
    return rows[-1][1]


class RuleEngine:
    def __init__(self, cfg, rng=None):
        self.cfg = cfg
        self.rng = rng or random.Random()
        self.paused = False
        self.reset(0)

    def reset(self, now):
        self.base = self.cfg['shock']['minBaseStrength']
        self.statuses = {'burning': False, 'flooding': False}
        self.dead = False
        self.active = False
        self.death_until = now
        self.death_strength = 0
        self.hit_started = float('-inf')
        self.hit_updated = now
        self.hit_total = 0
        self.hit_strength = 0
        self.hit_random = 0
        self.carry_strength = 0
        self.base_updated = now
        self.last_activity = now
        self.transient = None
        self.transient_until = now
        self.status_pulses = {}

    def stop(self, now):
        self.reset(now)
        self.paused = True

    def configure(self, cfg, now):
        self.cfg = cfg
        self.base = self._clamp_base(self.base)
        # Clear temporary output and pulse leases on a strategy change.
        self.hit_strength = 0
        self.transient = None
        self.status_pulses = {name: self.choose(cfg['rules'][name]['pulseId']) for name, active in self.statuses.items() if active}

    def choose(self, pulse):
        return self.rng.choice(pulse) if isinstance(pulse, list) else pulse

    def _clamp_base(self, value):
        return min(self.cfg['shock']['maxStrength'], max(self.cfg['shock']['minBaseStrength'], value))

    def recover_base(self, now):
        recovery = self.cfg['shock']['baseRecovery']
        if recovery['enabled'] and not self.paused and not self.dead:
            elapsed = max(0, now - max(self.base_updated, self.last_activity + recovery['delay']))
            self.base = self._clamp_base(self.base - elapsed * recovery['rate'])
        self.base_updated = now

    def transient_strength(self, now):
        hub = self.cfg['hub']
        decay = hub['decay']
        age = max(0, now - self.hit_updated)
        if not decay['enabled']:
            return self.hit_strength if age < hub['hit_duration'] else 0
        if age >= decay['max_duration']:
            return 0
        age = max(0, age - decay['hold_sec'])
        if decay['mode'] == 'linear':
            return max(0, self.hit_strength - age * decay['linear_rate'])
        if decay['mode'] == 'half_life':
            return math.floor(self.hit_strength * 2 ** (-age / decay['half_life']))
        return math.floor(self.hit_strength * decay['factor'] ** int(age / decay['interval']))

    def baseline_strength(self):
        penalties = sum(self.cfg['rules'][k]['strengthDelta'] for k, active in self.statuses.items() if active and self.cfg['rules'][k]['enabled'])
        return self._clamp_base(self.base + penalties)

    def damage(self, amount, maximum, now):
        if self.paused or self.dead or amount <= 0 or maximum <= 0:
            return
        if amount / maximum * 100 < self.cfg['shock']['minDamagePercent']:
            return
        self.recover_base(now)
        self.last_activity = now
        self.active = True
        if now - self.hit_started >= self.cfg['window_sec']:
            self.carry_strength = self.transient_strength(now)
            self.hit_started = now
            self.hit_total = 0
            self.base = self._clamp_base(self.base + self.cfg['shock']['addStrengthWhenHitInThisRound'])
            self.hit_random = self.rng.randint(*self.cfg['hub']['randomize_strength_range'])
        self.hit_total += amount
        self.hit_updated = now
        incoming = max(0, mapped_strength(100 * self.hit_total / maximum, self.cfg['hub']) * self.cfg['shock']['damageScale'] + self.hit_random)
        mode = self.cfg['shock']['retrigger']
        self.hit_strength = max(self.carry_strength, incoming) if mode == 'max' else self.carry_strength + incoming if mode == 'add' else incoming
        self.hit_strength = min(self.cfg['shock']['maxStrength'], self.hit_strength)
        LOG.info('受击 %.2f%%；本窗口累计 %.2f%%；基础值 %.2f', 100 * amount / maximum, 100 * self.hit_total / maximum, self.base)

    def _pulse(self, rule, now):
        selected = self.choose(rule['pulseId'])
        if selected:
            self.transient = selected
            self.transient_until = now + rule.get('pulseDuration', 4)

    def reward(self, name, count, now):
        rule = self.cfg['rules'][name]
        if self.paused or self.dead or not rule['enabled'] or count <= 0:
            return
        self.active = True
        self.recover_base(now)
        self.last_activity = now
        self.base = self._clamp_base(self.base + count * rule['strengthDelta'])
        self._pulse(rule, now)
        LOG.info('%s ×%d；基础值 %.2f', name, count, self.base)

    def status(self, name, active, now):
        if self.paused or self.dead:
            return
        if active != self.statuses[name]:
            self.statuses[name] = active
            self.active = True
            if active:
                self.status_pulses[name] = self.choose(self.cfg['rules'][name]['pulseId'])
            else:
                self.status_pulses.pop(name, None)

    def death(self, now):
        if self.paused or self.dead:
            return
        self.dead = True
        self.active = True
        rule = self.cfg['rules']['death']
        self.death_strength = (mapped_strength(100, self.cfg['hub']) + self.baseline_strength() + rule['strengthDelta'] + self.rng.randint(*self.cfg['hub']['randomize_strength_range'])) if rule['enabled'] else 0
        self.death_until = now + rule['duration'] if rule['enabled'] else now
        self.transient = None
        if rule['enabled']:
            self._pulse(rule, now)
        self.statuses = {'burning': False, 'flooding': False}
        self.status_pulses.clear()
        LOG.info('沉没；规则持续 %.2f 秒', max(0, self.death_until - now))

    def desired(self, now):
        if self.paused:
            return 0, None
        self.recover_base(now)
        default = self.cfg['shock']['defaultPulseId']
        selected = default
        for name in ('burning', 'flooding'):
            if self.statuses[name] and self.cfg['rules'][name]['enabled'] and self.status_pulses.get(name):
                selected = self.status_pulses[name]
        if self.transient and now < self.transient_until:
            selected = self.transient
        # A null default means leave Hub selection untouched. Temporary changes
        # then require a configured default (validated at save/startup).
        if self.dead:
            value = self.death_strength if now < self.death_until else 0
        elif not self.active:
            value = 0
        else:
            hub = self.cfg['hub']
            extra = self.transient_strength(now)
            floor = max(self.baseline_strength(), hub['decay']['min_strength'] if hub['decay']['enabled'] else 0)
            value = floor + extra
        return max(0, min(self.cfg['shock']['maxStrength'], math.ceil(value))), selected
