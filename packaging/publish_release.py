"""Publish a verified new-update build using the existing Git credential helper."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = 'dager33x/SystemOptiflow'
API = f'https://api.github.com/repos/{REPO}'


def session():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:
        credentials = subprocess.run(
            ['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
            text=True, capture_output=True, check=True, cwd=ROOT)
        fields = dict(line.split('=', 1) for line in credentials.stdout.splitlines() if '=' in line)
        token = fields.get('password')
    if not token:
        raise RuntimeError('GitHub sign-in is required to publish a release.')
    client = requests.Session()
    client.headers.update(Authorization=f'Bearer {token}', Accept='application/vnd.github+json',
                          **{'X-GitHub-Api-Version': '2022-11-28'})
    return client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--tag')
    args = parser.parse_args()
    client = session()
    response = client.get(API, timeout=60)
    response.raise_for_status()
    repo = response.json()
    if args.inspect:
        print(json.dumps({'repository': repo['full_name'], 'private': repo['private'],
                          'permissions': repo.get('permissions'), 'default_branch': repo['default_branch']}))
        return
    if not args.tag:
        parser.error('--tag is required when publishing')
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if branch != 'new-update':
        raise RuntimeError('Release must be built and published from new-update.')
    dist = ROOT / 'dist'
    manifest = json.loads((dist / 'SystemOptiflow_Release/BUILD-INFO.json').read_text(encoding='utf-8'))
    if manifest['branch'] != 'new-update' or manifest['uncommitted_source']:
        raise RuntimeError('Commit the release source and refresh the package first.')
    response = client.get(f'{API}/branches/new-update', timeout=60)
    response.raise_for_status()
    if response.json()['commit']['sha'] != manifest['commit']:
        raise RuntimeError('The built commit must be the remote new-update head.')
    archive = dist / 'SystemOptiflow-Windows-x64.zip'
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest not in (dist / 'SHA256SUMS.txt').read_text(encoding='utf-8'):
        raise RuntimeError('Release checksum mismatch.')
    notes = (
        'Windows 64-bit executable built exclusively from `new-update`.\n\n'
        'Download **SystemOptiflow-Windows-x64.zip**, extract the entire folder, '
        'and run **SystemOptiflow.exe**. Keep the `_internal` folder with the EXE. '
        'Python is included. CPU inference; no NVIDIA GPU required.\n\n'
        'For sign-in, copy `.env.example` to `.env` beside the EXE and configure '
        'your Supabase project locally. Email verification/reset also needs local SMTP configuration. '
        'Private credentials and incident evidence are not included. '
        '**Preview.cmd** opens the simulation without sign-in.\n\n'
        'Verified: login and dashboard rendering, bundled resources, writable data, '
        'frozen multiprocessing, CPU model inference, and adaptive model loading. '
        'Build is unsigned. See README-WINDOWS.txt for setup and data locations.\n\n'
        f'Source commit: `{manifest["commit"]}`. SHA256: `{digest}`.'
    )
    response = client.post(f'{API}/releases', timeout=60, json={
        'tag_name': args.tag, 'target_commitish': manifest['commit'],
        'name': f'SystemOptiflow Windows - new-update ({manifest["commit"][:7]})',
        'body': notes, 'draft': True, 'prerelease': True, 'make_latest': 'false',
    })
    response.raise_for_status()
    release = response.json()
    state = {'release_id': release['id'], 'tag': args.tag, 'url': release['html_url'], 'assets': []}
    (dist / 'github-release.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    upload_url = release['upload_url'].split('{', 1)[0]
    for path in (archive, dist / 'SHA256SUMS.txt'):
        print(f'Uploading {path.name} ({path.stat().st_size} bytes)', flush=True)
        with path.open('rb') as stream:
            response = client.post(upload_url, params={'name': path.name}, data=stream,
                                   headers={'Content-Type': 'application/octet-stream'}, timeout=(60, 900))
        response.raise_for_status()
        asset = response.json()
        if asset['state'] != 'uploaded' or asset['size'] != path.stat().st_size:
            raise RuntimeError('GitHub did not confirm the full upload.')
        state['assets'].append({'name': asset['name'], 'size': asset['size'], 'url': asset['browser_download_url']})
        (dist / 'github-release.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    response = client.patch(f'{API}/releases/{release["id"]}', json={'draft': False, 'make_latest': 'false'}, timeout=60)
    response.raise_for_status()
    state['url'] = response.json()['html_url']
    state['published'] = True
    (dist / 'github-release.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    print(json.dumps(state, indent=2))


if __name__ == '__main__':
    main()
