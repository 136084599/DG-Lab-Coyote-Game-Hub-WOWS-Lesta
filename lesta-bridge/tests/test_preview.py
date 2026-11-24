from copy import deepcopy
import unittest

from wows_bridge.config import validate
from wows_bridge.engine import RuleEngine
from wows_bridge.preview import simulate


class PreviewTests(unittest.TestCase):
    def cfg(self, **values):
        cfg = {'shock': {'addStrengthWhenHitInThisRound': 0},
               'hub': {'randomize_strength_range': [0, 0], 'Segment': [[0, 100]],
                       'decay': values}}
        return validate(cfg)

    def test_half_life_and_hold(self):
        e = RuleEngine(self.cfg(mode='half_life', half_life=1, hold_sec=.5))
        e.damage(5, 100, 0)
        self.assertEqual(e.desired(.5)[0], 100)
        self.assertEqual(e.desired(1.5)[0], 50)
        self.assertEqual(e.desired(2.5)[0], 25)

    def test_linear_and_duration_cap(self):
        e = RuleEngine(self.cfg(mode='linear', linear_rate=20, max_duration=3))
        e.damage(5, 100, 0)
        self.assertEqual(e.desired(1)[0], 80)
        self.assertEqual(e.desired(2)[0], 60)
        self.assertEqual(e.desired(3)[0], 0)

    def test_retrigger_add_without_double_count_in_same_window(self):
        cfg = self.cfg(mode='linear', linear_rate=10)
        cfg['hub']['Segment'] = [[0, 10], [2, 20], [5, 50]]
        cfg['shock']['retrigger'] = 'add'
        e = RuleEngine(cfg)
        e.damage(5, 100, 0)
        e.damage(1, 100, 1)
        self.assertEqual(e.desired(1)[0], 50)  # 40 remaining + 10 new
        e.damage(1, 100, 1.1)
        self.assertEqual(e.desired(1.1)[0], 60)  # previous-window 40 + aggregate 20

    def test_retrigger_max_keeps_stronger_remaining_effect(self):
        cfg = self.cfg(mode='linear', linear_rate=10)
        cfg['hub']['Segment'] = [[0, 10], [5, 50]]
        cfg['shock']['retrigger'] = 'max'
        e = RuleEngine(cfg)
        e.damage(5, 100, 0)
        e.damage(1, 100, 1)
        self.assertEqual(e.desired(1)[0], 40)

    def test_base_recovery_uses_elapsed_time_not_poll_count(self):
        cfg = self.cfg()
        cfg['shock']['baseRecovery'] = {'enabled': True, 'delay': 2, 'rate': 3}
        first, second = RuleEngine(cfg), RuleEngine(cfg)
        first.base = second.base = 20
        first.active = second.active = True
        for tick in range(501):
            first.desired(tick / 100)
        second.desired(5)
        self.assertAlmostEqual(first.base, 11)
        self.assertEqual(second.base, 11)

    def test_damage_filter_and_scale(self):
        cfg = self.cfg()
        cfg['shock']['minDamagePercent'] = 1
        cfg['shock']['damageScale'] = .5
        e = RuleEngine(cfg)
        e.damage(.5, 100, 0)
        self.assertEqual(e.desired(0)[0], 0)
        e.damage(1, 100, 1)
        self.assertEqual(e.desired(1)[0], 50)

    def test_preview_matches_engine_and_does_not_mutate_config(self):
        cfg = self.cfg(mode='linear', linear_rate=10)
        original = deepcopy(cfg)
        result = simulate(cfg, [{'time': 0, 'kind': 'damage', 'percent': 5}], 5)
        self.assertEqual(result['samples'][50]['strength'], 90)
        self.assertEqual(cfg, original)
        self.assertEqual(result, simulate(cfg, [{'time': 0, 'kind': 'damage', 'percent': 5}], 5))

    def test_invalid_events_and_tuning_are_rejected(self):
        for decay in [{'mode': 'unknown'}, {'half_life': 0}, {'hold_sec': 5, 'max_duration': 4}]:
            with self.assertRaises(ValueError):
                self.cfg(**decay)
        with self.assertRaises(ValueError):
            simulate(self.cfg(), [{'time': 0, 'kind': 'damage', 'percent': float('nan')}])


if __name__ == '__main__':
    unittest.main()
