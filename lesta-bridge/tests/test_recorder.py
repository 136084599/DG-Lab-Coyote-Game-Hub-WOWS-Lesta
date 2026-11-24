import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
import ast
from unittest.mock import patch


class RecorderTests(unittest.TestCase):
    def test_only_game_allowed_packages_are_imported(self):
        source = Path(__file__).resolve().parents[1] / 'mods/BattleRecorder/Main.py'
        tree = ast.parse(source.read_text('utf8'))
        imports = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        self.assertEqual(set(imports), {'datetime', 'time'})

    def test_one_repeating_timer_change_only_write_and_battle_end(self):
        with tempfile.TemporaryDirectory() as d:
            timers, cancelled = [], []
            state = {'id': 7, 'maxHealth': 1000, 'shipGameData': {'health': 1000}, 'shipId': 8, 'fragsCount': 0}
            def schedule(delay, callback):
                timers.append((delay, callback))
                return len(timers)
            modules = {
                'utils': types.SimpleNamespace(getModDir=lambda: d, logInfo=lambda *args: None),
                'battle': types.SimpleNamespace(getSelfPlayerInfo=lambda: state,
                    isVehicleBurning=lambda ship: False, isVehicleFlooding=lambda ship: False),
                'events': types.SimpleNamespace(onBattleStart=lambda cb: None,
                    onBattleQuit=lambda cb: None, onAchievementEarned=lambda cb: None),
                'callbacks': types.SimpleNamespace(callback=schedule, cancel=cancelled.append),
            }
            source = Path(__file__).resolve().parents[1] / 'mods/BattleRecorder/Main.py'
            with patch.dict(sys.modules, modules):
                spec = importlib.util.spec_from_file_location('test_game_recorder', source)
                mod = importlib.util.module_from_spec(spec)
                mod.__dict__.update(modules)
                spec.loader.exec_module(mod)
                self.assertIn('RecorderLoaded,', (Path(d) / 'damage_log.txt').read_text())
                r = mod.recorder
                r.init()
                log = Path(d) / 'damage_log.txt'
                original = log.read_text()
                self.assertIn('BattleStart,', original)
                r.update()
                self.assertEqual(log.read_text(), original)
                self.assertEqual(len(timers), 1)
                r.last_write = 0
                r.update()
                self.assertGreater(len(log.read_text()), len(original))
                r.achievement(None, 9)
                r.achievement(None, 7)
                state['shipGameData']['health'] = 900
                r.update()
                self.assertIn('Achievements:1', log.read_text())
                self.assertIn(',900,isDied:', log.read_text())
                r.destructor()
                self.assertTrue(log.read_text().endswith('BattleEnd\n'))
                self.assertEqual(cancelled, [1])


if __name__ == '__main__':
    unittest.main()
