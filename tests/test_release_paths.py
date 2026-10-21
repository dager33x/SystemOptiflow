import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from dashboard.utils.paths import get_config_paths, get_data_path, load_environment


class ReleasePaths(unittest.TestCase):
    def test_frozen_records_are_outside_install_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, 'frozen', True, create=True):
            with patch.dict(os.environ, {'LOCALAPPDATA': folder}, clear=True):
                self.assertEqual(Path(get_data_path('dashboard.log')), Path(folder) / 'SystemOptiflow/dashboard.log')

    def test_frozen_configuration_is_beside_executable_not_working_directory(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sys, 'frozen', True, create=True):
            exe = Path(folder) / 'application/SystemOptiflow.exe'
            with patch.object(sys, 'executable', str(exe)), patch.dict(os.environ, {'OPTIFLOW_DATA_DIR': str(Path(folder) / 'data')}):
                self.assertEqual(get_config_paths(), (exe.parent / '.env', Path(folder) / 'data/.env'))

    def test_explicit_environment_takes_priority_over_configuration_file(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / '.env'
            config.write_text('RELEASE_TEST_KEY=from-file\n', encoding='utf-8')
            with patch('dashboard.utils.paths.get_config_paths', return_value=(config,)):
                with patch.dict(os.environ, {'RELEASE_TEST_KEY': 'from-environment'}):
                    self.assertEqual(load_environment(), str(config))
                    self.assertEqual(os.environ['RELEASE_TEST_KEY'], 'from-environment')


if __name__ == '__main__':
    unittest.main()
