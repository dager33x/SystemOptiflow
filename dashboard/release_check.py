"""Offline release verification, invoked explicitly with --self-test DIRECTORY."""
import json
import os
from pathlib import Path
import time
import traceback


def run(output_directory):
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'ok': False, 'checks': []}
    worker = None
    controller = None
    try:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        import multiprocessing as mp
        import numpy as np
        import torch
        import cv2
        import supabase
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont, QFontDatabase
        from dashboard.controllers.app_controller import AppManager
        from dashboard.controllers.dashboard_controller import DashboardController
        from dashboard.views.main_window import DashboardWindow
        from dashboard.services.workers import inference_process
        from dashboard.utils.paths import get_resource_path, get_data_path

        for name in ('Model.pt', 'yolov8n.pt', 'smart_traffic_dqn.zip',
                     'assets/logo.png', 'assets/login_reference.png',
                     'assets/sounds/incident.wav', 'assets/sounds/violation.wav'):
            assert Path(get_resource_path(name)).is_file(), name
        probe = Path(get_data_path('write-test.txt'))
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        report['checks'].append('bundled resources and writable user data')

        app = QApplication.instance() or QApplication([])
        app.setApplicationName('SystemOptiflow Release Check')
        # The offscreen Qt platform does not discover Windows system fonts.
        fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('segoeui.ttf', 'segoeuib.ttf', 'consola.ttf', 'consolab.ttf'):
            if (fonts / name).is_file():
                QFontDatabase.addApplicationFont(str(fonts / name))
        app.setFont(QFont('Segoe UI', 10))
        manager = AppManager(app)
        deadline = time.monotonic() + 20
        while manager.auth is None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.05)
        assert manager.auth is not None, manager.login.status.text()
        assert manager.login.grab().save(str(output / 'login.png'))
        manager.login.hide()
        report['checks'].append('login window and configuration initialization')

        controller = DashboardController()
        window = DashboardWindow(controller, autostart=False)
        window.show()
        app.processEvents()
        assert window.grab().save(str(output / 'dashboard.png'))
        window.hide()
        report['checks'].append('dashboard rendering')

        # Exercise the real spawn path: frozen children must not open another GUI.
        ctx = mp.get_context('spawn')
        requests, responses = ctx.Queue(2), ctx.Queue(4)
        worker = ctx.Process(target=inference_process, args=(requests, responses, 'all'))
        worker.start()
        ready = responses.get(timeout=120)
        assert ready[0] == 'ready', ready
        requests.put((0, 0, 1, time.monotonic(), np.zeros((320, 320, 3), np.uint8)))
        result = responses.get(timeout=120)
        assert result[0] == 'result' and result[7], result[:4]
        requests.put(None)
        worker.join(20)
        assert worker.exitcode == 0, worker.exitcode
        report['checks'].append('frozen multiprocessing, Model.pt load and CPU inference')

        from dashboard.models.detection.traffic_controller import TrafficLightController
        traffic = TrafficLightController(use_pretrained=False, detector=object())
        loaded = None
        for name in ('smart_traffic_dqn.zip', 'Optiflow_Dqn.pth',
                     'checkpoints/dqn/dqn_best.pth', 'checkpoints/dqn/dqn_final.pth'):
            if traffic.dqn.load_model(get_resource_path(name)):
                loaded = name
                break
        assert loaded, 'No compatible adaptive traffic checkpoint loaded'
        report['traffic_checkpoint'] = loaded
        report['checks'].append('adaptive traffic model load')
        report['versions'] = {'torch': torch.__version__, 'opencv': cv2.__version__}
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if worker is not None and worker.is_alive():
            worker.terminate()
            worker.join(10)
        if controller is not None:
            controller.stop()
        (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
