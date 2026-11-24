from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

import launcher
from wows_bridge.config import validate


class LauncherTests(unittest.TestCase):
    def test_missing_hub_still_opens_diagnostic_console(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('sys.argv', ['launcher.py']), patch('launcher.load', return_value=validate({})), \
                 patch('launcher.urlopen', side_effect=URLError('offline')), patch('launcher.ready', return_value=False), \
                 patch('launcher.HUB_DIR', Path(d) / 'missing'), patch('wows_bridge.app.main') as run:
                self.assertEqual(launcher.main(), 0)
                run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
