from pathlib import Path
import tempfile
import unittest
from wows_bridge.streaming import THEMES, client_id, viewer_link, saved_sessions


class StreamingTests(unittest.TestCase):
    def test_original_viewer_routes_and_query_order(self):
        for theme in THEMES:
            result = viewer_link('http://localhost:8920/', 'abc-123', theme['id'])
            self.assertIn('http://127.0.0.1:8920/viewer.html?clientId=abc-123#/', result['url'])
            self.assertEqual(result['width'], theme['width'])
        self.assertTrue(viewer_link('http://localhost:8920', 'x', 'circle')['url'].endswith('#/?darkMode=true'))

    def test_paste_old_link_only_extracts_id(self):
        result = viewer_link('http://localhost:8920', 'https://other.example/viewer.html?clientId=real-id#/battery1', 'bar')
        self.assertEqual(result['url'], 'http://127.0.0.1:8920/viewer.html?clientId=real-id#/bar1')

    def test_broadcast_and_injected_ids_rejected(self):
        for value in ['all', 'all.channelB', '', 'x&admin=true', '../x', '<script>']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                client_id(value)

    def test_saved_session_files_are_not_modified(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'data/game-config'
            root.mkdir(parents=True)
            file = root / 'saved-id.main-game.json'
            file.write_text('{"custom":"untouched"}')
            self.assertEqual(saved_sessions(d), ['saved-id'])
            self.assertEqual(file.read_text(), '{"custom":"untouched"}')


if __name__ == '__main__':
    unittest.main()
