"""Review rules, response progression, audit integrity, and stale-write checks."""
from pathlib import Path
import sys
import tempfile
import json
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.models.incident_workflow import workflow_change, normalize_incident
from dashboard.models.local_incidents import LocalIncidents
from dashboard.controllers.accident_controller import AccidentController
from dashboard.models.database import TrafficDB

ACTOR = {'user_id': 'personnel', 'username': 'Officer Reyes', 'role': 'operator',
         'approval_status': 'approved', 'is_active': True}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.row = normalize_incident({'accident_id': 'incident'})

    def apply(self, action, value, note='Reviewed camera and checked the scene.'):
        change = workflow_change(self.row, ACTOR, action, value, note)
        self.row.update(change)
        return change

    def test_full_response_keeps_every_action_and_person(self):
        self.apply('review', 'confirmed')
        for stage in ('acknowledged', 'responding', 'resolved'):
            self.apply('response', stage)
        self.assertEqual(self.row['response_status'], 'resolved')
        self.assertEqual(len(self.row['workflow_history']), 4)
        self.assertEqual(self.row['workflow_version'], 4)
        self.assertTrue(all(e['actor_id'] == ACTOR['user_id'] and e['at'] for e in self.row['workflow_history']))
        self.assertEqual(self.row['response_by_name'], 'Officer Reyes')

    def test_false_detection_closes_without_dispatch(self):
        self.apply('review', 'false_detection')
        self.assertEqual(self.row['response_status'], 'resolved')
        with self.assertRaises(ValueError):
            self.apply('response', 'acknowledged')

    def test_correcting_false_detection_reopens_with_history(self):
        self.apply('review', 'false_detection')
        self.apply('review', 'needs_investigation', 'New evidence; reopen for investigation.')
        self.assertEqual(self.row['response_status'], 'pending')
        self.assertEqual(len(self.row['workflow_history']), 2)

    def test_investigation_can_acknowledge_and_respond_but_not_resolve(self):
        self.apply('review', 'needs_investigation')
        self.apply('response', 'acknowledged')
        self.apply('response', 'responding')
        with self.assertRaises(ValueError):
            self.apply('response', 'resolved')
        self.apply('review', 'confirmed')
        self.apply('response', 'resolved')

    def test_cannot_skip_or_reverse_response(self):
        for value in ('responding', 'resolved', 'pending'):
            with self.assertRaises(ValueError):
                self.apply('response', value)
        self.apply('response', 'acknowledged')
        with self.assertRaises(ValueError):
            self.apply('response', 'pending')

    def test_notes_and_decisions_validated(self):
        for note in ('', ' ', 'x'*1001):
            with self.assertRaises(ValueError):
                self.apply('review', 'confirmed', note)
        for value in ('unknown', 'unreviewed'):
            with self.assertRaises(ValueError):
                self.apply('review', value)
        self.apply('review', 'confirmed')
        with self.assertRaises(ValueError):
            self.apply('review', 'confirmed')

    def test_unauthorized_personnel_denied(self):
        for actor in (None, dict(ACTOR, role='viewer'), dict(ACTOR, approval_status='pending'), dict(ACTOR, is_active=False)):
            with self.assertRaises(ValueError):
                workflow_change(self.row, actor, 'review', 'confirmed', 'Note')

    def test_history_input_not_mutated(self):
        first = self.apply('review', 'confirmed')
        old_history = first['workflow_history']
        self.apply('response', 'acknowledged')
        self.assertEqual(len(old_history), 1)

    def test_legacy_resolved_record_not_reopened_by_normalization(self):
        row = normalize_incident({'status': 'resolved', 'created_at': '2026-09-30'})
        self.assertEqual(row['response_status'], 'resolved')
        self.assertEqual(row['timestamp'], '2026-09-30')


class LocalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'incidents.json'
        self.repo = LocalIncidents(self.path)
        self.repo.append({'lane': 0, 'description': 'Original evidence', 'image_url': 'evidence.jpg'})
        self.row = self.repo.read()[0]

    def test_saved_state_and_history_survive_reload(self):
        self.repo.update(self.row['accident_id'], 0, ACTOR, 'review', 'confirmed', 'Scene checked')
        result = LocalIncidents(self.path).read()[0]
        self.assertEqual(result['workflow_version'], 1)
        self.assertEqual(result['image_url'], 'evidence.jpg')
        self.assertEqual(result['description'], 'Original evidence')

    def test_concurrent_updates_do_not_overwrite(self):
        def change(value):
            try:
                self.repo.update(self.row['accident_id'], 0, ACTOR, 'review', value, 'Checked footage')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(2) as executor:
            results = list(executor.map(change, ('confirmed', 'false_detection')))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(self.repo.read()[0]['workflow_history']), 1)

    def test_old_local_records_get_stable_ids(self):
        self.path.write_text(json.dumps([{'lane': 1}]), encoding='utf-8')
        self.assertEqual(self.repo.read()[0]['accident_id'], self.repo.read()[0]['accident_id'])

    def test_corrupt_file_not_overwritten(self):
        self.path.write_text('broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.repo.append({'lane': 2})
        self.assertEqual(self.path.read_text(), 'broken')

    def test_controller_routes_local_and_remote_separately(self):
        db = Mock()
        controller = AccidentController(db, current_user=lambda: ACTOR)
        controller._app_path = lambda *parts: str(self.path)
        controller.update_workflow(self.row['accident_id'], 0, 'review', 'false_detection', 'No crash')
        db.update_incident_workflow.assert_not_called()
        controller.update_workflow('remote-id', 3, 'review', 'confirmed', 'Verified')
        db.update_incident_workflow.assert_called_once_with('remote-id', 3, 'personnel', 'review', 'confirmed', 'Verified')

    def test_controller_includes_offline_records_alongside_database(self):
        db = Mock()
        db.get_recent_accidents.return_value = [{'accident_id': 'remote', 'created_at': '2026-09-30'}]
        controller = AccidentController(db)
        controller._app_path = lambda *parts: str(self.path) if parts[0] == 'accident_logs_local.json' else str(Path(self.temp.name)/'missing.json')
        self.assertEqual(len(controller.get_incidents()), 2)


class DatabaseWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.db = TrafficDB.__new__(TrafficDB)
        self.db.logger = Mock()
        self.db.get_user_by_id = Mock(return_value=ACTOR)
        self.db.supabase = Mock()
        self.query = self.db.supabase.table.return_value
        for name in ('select', 'eq', 'update'):
            getattr(self.query, name).return_value = self.query
        self.row = normalize_incident({'accident_id': 'remote'})

    def test_state_and_audit_saved_atomically_with_version_guard(self):
        self.query.execute.side_effect = [SimpleNamespace(data=[self.row]), SimpleNamespace(data=[{'workflow_version': 1}])]
        self.db.update_incident_workflow('remote', 0, 'personnel', 'review', 'confirmed', 'Verified')
        self.query.eq.assert_any_call('workflow_version', 0)
        payload = self.query.update.call_args.args[0]
        self.assertEqual(payload['review_status'], 'confirmed')
        self.assertEqual(len(payload['workflow_history']), 1)
        self.assertEqual(payload['reviewed_by'], 'personnel')

    def test_stale_version_and_concurrent_save_rejected(self):
        self.query.execute.return_value = SimpleNamespace(data=[dict(self.row, workflow_version=2)])
        with self.assertRaisesRegex(ValueError, 'Another person'):
            self.db.update_incident_workflow('remote', 0, 'personnel', 'review', 'confirmed', 'Verified')
        self.query.update.assert_not_called()
        self.query.execute.side_effect = [SimpleNamespace(data=[self.row]), SimpleNamespace(data=[])]
        with self.assertRaisesRegex(ValueError, 'changed while saving'):
            self.db.update_incident_workflow('remote', 0, 'personnel', 'review', 'confirmed', 'Verified')

    def test_schema_missing_does_not_write_a_fake_success(self):
        self.query.execute.return_value = SimpleNamespace(data=[{'accident_id': 'remote'}])
        with self.assertRaisesRegex(ValueError, 'migration'):
            self.db.update_incident_workflow('remote', 0, 'personnel', 'review', 'confirmed', 'Verified')
        self.query.update.assert_not_called()

    def test_demoted_or_inactive_account_cannot_update(self):
        self.db.get_user_by_id.return_value = dict(ACTOR, is_active=False)
        self.query.execute.return_value = SimpleNamespace(data=[self.row])
        with self.assertRaises(ValueError):
            self.db.update_incident_workflow('remote', 0, 'personnel', 'review', 'confirmed', 'Verified')
        self.query.update.assert_not_called()


if __name__ == '__main__':
    unittest.main()
