from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import socket

from wows_bridge.discovery import discover, inspect_game, steam_candidates
from wows_bridge.setup import install_recorder


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / '我的游戏 Korabli'
        (self.game / 'bin/9/bin64').mkdir(parents=True)
        (self.game / 'bin/10/bin64').mkdir(parents=True)
        (self.game / 'Korabli.exe').touch()

    def test_root_exe_and_bin64_normalize_to_latest_numeric_build(self):
        for value in [self.game, self.game / 'Korabli.exe', self.game / 'bin/9/bin64']:
            info = inspect_game(str(value))
            self.assertTrue(info['valid'])
            self.assertEqual(info['path'], str(self.game))
            self.assertEqual(info['version'], '10')
            self.assertFalse(info['mod_installed'])

    def test_random_folder_is_not_a_game(self):
        self.assertFalse(inspect_game(str(self.root))['valid'])
        self.assertFalse(inspect_game('')['valid'])

    def test_installed_build_precedes_higher_preload_directory(self):
        from wows_bridge.config import log_path
        (self.game / 'game_info.xml').write_text('<protocol><part_versions><version name="client" installed="26.11.1.0.9" available="26.11.1.0.10"/></part_versions></protocol>')
        self.assertEqual(inspect_game(str(self.game))['version'], '9')
        self.assertIn('9', log_path({'wows_path': str(self.game), 'log_path': ''}).parts)
        (self.game / 'game_info.xml').write_text('<protocol><part_versions><version name="client" installed="26.11.1.0.8"/></part_versions></protocol>')
        self.assertFalse(inspect_game(str(self.game))['valid'])

    def test_loader_marker_is_created_but_existing_loader_is_preserved(self):
        info = inspect_game(str(self.game))
        loader = Path(info['loader_path'])
        with patch('wows_bridge.setup.running_games', return_value=[]):
            result = install_recorder(str(self.game))
            self.assertTrue(result['loader_created'])
            self.assertEqual(loader.read_bytes(), b'')
            loader.write_text('# another mod loader')
            install_recorder(str(self.game))
        self.assertEqual(loader.read_text(), '# another mod loader')
        self.assertTrue(inspect_game(str(self.game))['mod_installed'])

    def test_busy_console_port_does_not_start_output_lifecycle(self):
        from wows_bridge.app import main
        from wows_bridge.config import save, validate
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            cfg = validate({'web_port': listener.getsockname()[1], 'log_path': str(self.root / 'log.txt')})
            file = self.root / 'config.yaml'
            save(file, cfg)
            with patch('sys.argv', ['main.py', '--config', str(file), '--dry-run']), patch('wows_bridge.app.web.run_app') as run:
                with self.assertRaises(SystemExit) as result:
                    main()
                self.assertEqual(result.exception.code, 2)
                run.assert_not_called()

    def test_dedup_discovery_and_manual_candidates(self):
        with patch('wows_bridge.discovery.registry_candidates', return_value=[]), patch('wows_bridge.discovery.common_candidates', return_value=[]):
            result = discover(str(self.game), [(self.game / 'bin/9/bin64', '手动路径')])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source'], '已保存目录')

    def test_steam_separate_library_and_unicode_install_dir(self):
        steam = self.root / 'Steam'
        library = self.root / '新游戏库'
        (steam / 'steamapps').mkdir(parents=True)
        (library / 'steamapps').mkdir(parents=True)
        escaped = str(library).replace('\\', '\\\\')
        (steam / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "' + escaped + '" } }', encoding='utf8')
        (library / 'steamapps/appmanifest_552990.acf').write_text('"AppState" { "installdir" "我的战舰" }', encoding='utf8')
        self.assertIn(library / 'steamapps/common/我的战舰', list(steam_candidates(steam)))

    def test_installer_backup_idempotence_and_running_game_rejection(self):
        destination = Path(inspect_game(str(self.game))['mod_path'])
        destination.parent.mkdir(parents=True)
        destination.write_text('original')
        with patch('wows_bridge.setup.running_games', return_value=['Korabli.exe']):
            with self.assertRaises(ValueError):
                install_recorder(str(self.game))
        self.assertEqual(destination.read_text(), 'original')
        with patch('wows_bridge.setup.running_games', return_value=[]):
            result = install_recorder(str(self.game))
            self.assertEqual(Path(result['backup']).read_text(), 'original')
            again = install_recorder(str(self.game))
            self.assertIsNone(again['backup'])
        self.assertIn('BattleRecorder', destination.read_text())


if __name__ == '__main__':
    unittest.main()
