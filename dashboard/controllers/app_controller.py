"""Application lifecycle and authentication coordination."""
from PySide6.QtCore import QObject
from dashboard.services.tasks import TaskRunner, Messages
from dashboard.views.auth_window import AuthWindow
from dashboard.views.main_window import DashboardWindow
from dashboard.controllers.dashboard_controller import DashboardController


class AppManager(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.auth, self.db = app, None, None
        self.runner = TaskRunner(self)
        self.dashboard = None
        self.login = AuthWindow(self)
        self.login.show()
        def initialize():
            from dashboard.models.database import TrafficDB
            from dashboard.controllers.auth_controller import AuthController
            db = TrafficDB()
            return db, AuthController(db, notifier=Messages())
        self.runner.submit(initialize, self.initialized)
        app.aboutToQuit.connect(self.stop)

    def initialized(self, result, error):
        if error:
            self.login.status.setText('Startup failed: ' + error)
            return
        self.db, self.auth = result
        self.login.submit_button.setEnabled(True)
        self.login.status.setText('' if self.db.is_connected() else 'Database unavailable. Check the existing Supabase configuration before signing in.')

    def show_dashboard(self):
        controller = DashboardController(self.db, configured=True, current_user=self.auth.get_current_user)
        self.dashboard = DashboardWindow(controller, db=self.db, auth=self.auth,
            current_user=self.auth.get_current_user(), runner=self.runner)
        self.dashboard.logout_requested.connect(self.logout)
        self.dashboard.showMaximized()
        self.login.hide()

    def logout(self):
        self.login.show_form('login')
        self.login.show()
        self.dashboard.close()
        self.dashboard.deleteLater()
        self.dashboard = None
        self.auth.logout()

    def stop(self):
        if self.dashboard:
            self.dashboard.controller.stop()

