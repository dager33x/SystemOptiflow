"""Offline checks for the MVC package migration."""
import ast
import importlib
import os
from pathlib import Path
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
files = list((root / 'dashboard').rglob('*.py')) + [root / 'app.py', root / 'run_training.py']
for path in files:
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('dashboard.'):
            module_path = root.joinpath(*node.module.split('.'))
            assert module_path.with_suffix('.py').exists() or (module_path / '__init__.py').exists(), (path, node.module)
print(f'Parsed {len(files)} Python files; internal import targets exist.')
for path in (root / 'dashboard').rglob('*.py'):
    module = '.'.join(path.relative_to(root).with_suffix('').parts)
    importlib.import_module(module.removesuffix('.__init__'))
assert 'tkinter' not in sys.modules
from dashboard.utils.paths import get_resource_path
assert Path(get_resource_path('best.pt')) == root / 'best.pt'
from dashboard.controllers.accident_controller import AccidentController
from dashboard.controllers.violation_controller import ViolationController
for cls in (AccidentController, ViolationController):
    assert Path(cls(None)._app_path('screenshots')) == root / 'screenshots'
from PySide6.QtWidgets import QApplication
from dashboard.controllers.dashboard_controller import DashboardController
from dashboard.views.main_window import DashboardWindow
from dashboard.views.auth_window import AuthWindow
app = QApplication([])
controller = DashboardController()
window = DashboardWindow(controller, autostart=False)
window.show()
app.processEvents()
window.close()
class Manager:
    auth = None
login = AuthWindow(Manager())
for mode in ('login', 'signup', 'forgot', 'verify', 'reset'):
    login.show_form(mode)
    app.processEvents()
login.close()
print('All dashboard modules imported; resource paths and Qt dashboard/auth forms passed without starting cameras or database connections.')
