"""Qt application entry point."""
import logging
import multiprocessing
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from dashboard.controllers.app_controller import AppManager
from dashboard.controllers.dashboard_controller import DashboardController
from dashboard.views.main_window import DashboardWindow
from dashboard.utils.paths import get_data_path


def main():
    multiprocessing.freeze_support()
    logging.basicConfig(level=logging.WARNING,
        filename=get_data_path('dashboard.log'),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app = QApplication(sys.argv)
    app.setApplicationName('SystemOptiflow')
    app.setOrganizationName('Optiflow')
    if '--preview' in sys.argv:
        controller = DashboardController()
        window = DashboardWindow(controller)
        window.showMaximized()
        app.aboutToQuit.connect(controller.stop)
    else:
        manager = AppManager(app)
    return app.exec()
