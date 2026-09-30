"""Incident review/response rules shared by database and local records."""
from datetime import datetime, timezone
from dashboard.models.user import User

REVIEWS = {'unreviewed': 'Unreviewed', 'confirmed': 'Confirmed',
           'false_detection': 'False detection', 'needs_investigation': 'Needs investigation'}
RESPONSES = {'pending': 'Pending', 'acknowledged': 'Acknowledged',
             'responding': 'Responding', 'resolved': 'Resolved'}


def normalize_incident(row):
    row = dict(row)
    legacy = str(row.get('status', '')).lower()
    row.setdefault('review_status', 'unreviewed')
    row.setdefault('response_status', 'resolved' if row.get('resolved') or legacy in ('resolved', 'closed') else 'pending')
    row.setdefault('workflow_version', 0)
    row.setdefault('workflow_history', [])
    row['timestamp'] = row.get('timestamp') or row.get('created_at') or ''
    return row


def workflow_change(row, actor, action, value, note, timestamp=None):
    if not actor or actor.get('role') not in ('admin', 'operator') or not User.can_sign_in(actor) or not actor.get('user_id'):
        raise ValueError('Only signed-in, approved traffic personnel can update incidents.')
    note = note.strip()
    if not 1 <= len(note) <= 1000:
        raise ValueError('Enter a note between 1 and 1,000 characters.')
    row = normalize_incident(row)
    before_review, before_response = row['review_status'], row['response_status']
    review, response = before_review, before_response
    if action == 'review':
        if value not in REVIEWS or value == 'unreviewed' or value == review:
            raise ValueError('Choose a different review decision.')
        review = value
        if review == 'false_detection':
            response = 'resolved'
        elif before_review == 'false_detection' or (review == 'needs_investigation' and response == 'resolved'):
            response = 'pending'
    elif action == 'response':
        if review == 'false_detection':
            raise ValueError('This alert was dismissed. Review it again before reopening the response.')
        next_status = {'pending': 'acknowledged', 'acknowledged': 'responding', 'responding': 'resolved'}
        if next_status.get(response) != value:
            raise ValueError('Response must progress Pending → Acknowledged → Responding → Resolved.')
        if value == 'resolved' and review != 'confirmed':
            raise ValueError('Confirm the incident or dismiss it as a false detection before resolving it.')
        response = value
    else:
        raise ValueError('Unknown incident action.')
    when = timestamp or datetime.now(timezone.utc).isoformat()
    name = actor.get('username') or actor['user_id']
    version = row['workflow_version'] + 1
    entry = {'version': version, 'action': action, 'review_from': before_review, 'review_to': review,
             'response_from': before_response, 'response_to': response, 'note': note,
             'actor_id': actor['user_id'], 'actor_name': name, 'at': when}
    update = {'review_status': review, 'response_status': response, 'workflow_version': version,
              'workflow_history': list(row['workflow_history']) + [entry]}
    if action == 'review':
        update.update(reviewed_by=actor['user_id'], reviewed_by_name=name, reviewed_at=when, review_note=note)
    if action == 'response' or response != before_response:
        update.update(response_by=actor['user_id'], response_by_name=name, response_at=when, response_note=note)
    return update
