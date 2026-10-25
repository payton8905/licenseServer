#!/usr/bin/env python3
"""Exercise the real CE REST API; keep reusable PoC fixtures in .runtime."""
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import ssl
import urllib.error
import urllib.request

from poc import ROOT, RUNTIME, LocalConnectionError, local_open

ENV = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines() if '=' in line)
BASE = 'https://localhost:8443/v1/accounts/' + ENV['KEYGEN_ACCOUNT_ID']
TLS = ssl.create_default_context(cafile=str(RUNTIME / 'root.crt'))
TOKEN = None


def request(method, path, body=None, *, auth=None, expected=(200, 201, 202, 204)):
    headers = {'Accept': 'application/vnd.api+json', 'Content-Type': 'application/vnd.api+json', 'Keygen-Version': '1.8'}
    if auth or TOKEN:
        headers['Authorization'] = auth or ('Bearer ' + TOKEN)
    req = urllib.request.Request(BASE + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        response = local_open(req, context=TLS, timeout=15)
    except urllib.error.HTTPError as err:
        response = err
    with response:
        raw = response.read()
        result = json.loads(raw) if raw else {}
        if response.status not in expected:
            # Never dump successful token/license responses into logs.
            raise RuntimeError(f'{method} {path}: {response.status}: {result.get("errors", [])}')
        return result


def create(kind, attrs, relationships=None):
    data = {'type': kind, 'attributes': attrs}
    if relationships:
        data['relationships'] = {key: {'data': {'type': typ, 'id': rid}} for key, (typ, rid) in relationships.items()}
    return request('POST', '/' + kind, {'data': data})['data']


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump(value, out, indent=2)


def main():
    global TOKEN
    credentials = base64.b64encode((ENV['KEYGEN_ADMIN_EMAIL'] + ':' + ENV['KEYGEN_ADMIN_PASSWORD']).encode()).decode()
    token = request('POST', '/tokens', {'data': {'type': 'tokens', 'attributes': {
        'name': 'Local PoC verification',
        'expiry': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }}}, auth='Basic ' + credentials)['data']
    TOKEN = token['attributes']['token']
    try:
        print('PASS admin password authentication / API 1.8')
        account = request('GET', '')['data']
        # API 1.8 transports the hexadecimal Ed25519 key inside Base64.
        public_key = base64.b64decode(account['meta']['keys']['ed25519'], validate=True).decode('ascii')
        assert len(bytes.fromhex(public_key)) == 32
        (RUNTIME / 'ed25519-public-key.txt').write_text(public_key + '\n')
        fixtures = RUNTIME / 'fixtures.json'
        if fixtures.exists():
            state = json.loads(fixtures.read_text())
        else:
            product = create('products', {'name': 'SBOMScan PoC', 'metadata': {'poc': True}})
            state = {'product': product['id'], 'policies': {}, 'licenses': {}}
            private_json(fixtures, state)
        for tier in ['Basic', 'Professional', 'Enterprise']:
            if tier not in state['policies']:
                policy = create('policies', {
                    'name': tier + ' PoC (test limits only)', 'duration': 2592000,
                    'scheme': 'ED25519_SIGN', 'strict': True, 'floating': False,
                    'maxMachines': 1, 'maxProcesses': 2,
                    'metadata': {'poc': True, 'commercialPlanDefined': False},
                }, {'product': ('products', state['product'])})
                state['policies'][tier] = policy['id']
                private_json(fixtures, state)
        if 'entitlement' not in state:
            entitlement = create('entitlements', {'name': 'PoC scanning module', 'code': 'POC_SCAN'})
            state['entitlement'] = entitlement['id']
            private_json(fixtures, state)
        attached = request('GET', '/policies/' + state['policies']['Basic'] + '/entitlements')['data']
        if not any(item['id'] == state['entitlement'] for item in attached):
            request('POST', '/policies/' + state['policies']['Basic'] + '/entitlements',
                    {'data': [{'type': 'entitlements', 'id': state['entitlement']}]})
        if 'Basic' not in state['licenses']:
            lic = create('licenses', {'name': 'PoC offline test', 'expiry':
                         (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()},
                         {'policy': ('policies', state['policies']['Basic'])})
            state['licenses']['Basic'] = {'id': lic['id'], 'key': lic['attributes']['key']}
            private_json(fixtures, state)
        lic = state['licenses']['Basic']
        if 'machine' not in state:
            machine = create('machines', {'fingerprint': 'sbomscan-poc-host-001', 'name': 'Offline PoC host'},
                             {'license': ('licenses', lic['id'])})
            state['machine'] = machine['id']
            private_json(fixtures, state)
        result = request('POST', '/licenses/' + lic['id'] + '/actions/validate',
                         {'meta': {'scope': {'fingerprint': 'sbomscan-poc-host-001'}}})
        assert result['meta']['valid'] is True, result['meta']
        print('PASS license validation for activated fingerprint')
        result = request('POST', '/licenses/' + lic['id'] + '/actions/validate',
                         {'meta': {'scope': {'fingerprint': 'sbomscan-poc-wrong-host'}}})
        assert result['meta']['valid'] is False, result['meta']
        print('PASS different fingerprint rejected')
        result = request('POST', '/machines', {'data': {'type': 'machines', 'attributes': {
            'fingerprint': 'sbomscan-poc-host-over-limit'}, 'relationships': {
            'license': {'data': {'type': 'licenses', 'id': lic['id']}}}}}, expected=(422,))
        assert any('LIMIT' in e.get('code', '') for e in result['errors']), result['errors']
        print('PASS second deployment rejected (maxMachines=1)')
        # Processes are test leases, not yet actual application user sessions.
        processes = []
        try:
            for pid in ['poc-session-1', 'poc-session-2']:
                process = create('processes', {'pid': pid}, {'machine': ('machines', state['machine'])})
                processes.append(process['id'])
            result = request('POST', '/processes', {'data': {'type': 'processes', 'attributes': {
                'pid': 'poc-session-over-limit'}, 'relationships': {
                'machine': {'data': {'type': 'machines', 'id': state['machine']}}}}}, expected=(422,))
            assert any('LIMIT' in e.get('code', '') for e in result['errors']), result['errors']
            print('PASS third process rejected (maxProcesses=2; Session integration pending)')
        finally:
            for process_id in processes:
                request('DELETE', '/processes/' + process_id)
        result = request('POST', '/machines/' + state['machine'] +
                         '/actions/check-out?algorithm=base64%2Bed25519&include=license,license.entitlements&ttl=2592000')
        certificate = result['data']['attributes']['certificate']
        fd = os.open(RUNTIME / 'machine.lic', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(certificate)
        print('PASS CE machine-file checkout (30-day TTL)')
        from verify_offline import verify
        document = verify(certificate, public_key, 'sbomscan-poc-host-001')
        assert any(item['type'] == 'entitlements' and item['attributes']['code'] == 'POC_SCAN'
                   for item in document.get('included', [])), 'Entitlement missing from signed file'
        print('PASS offline signature, device, expiry and signed entitlement (no API calls)')
        import copy
        envelope = json.loads(base64.b64decode(''.join(certificate.strip().splitlines()[1:-1])))
        tampered = copy.deepcopy(envelope)
        tampered['enc'] = base64.b64encode(b'{"forged":true}').decode()
        forged = '-----BEGIN MACHINE FILE-----\n' + base64.b64encode(json.dumps(tampered).encode()).decode() + '\n-----END MACHINE FILE-----'
        for label, contents, fingerprint, instant in [
            ('modified payload', forged, 'sbomscan-poc-host-001', None),
            ('copied file on another device', certificate, 'another-device', None),
            ('expired file', certificate, 'sbomscan-poc-host-001', datetime.now(timezone.utc) + timedelta(days=31)),
        ]:
            try:
                verify(contents, public_key, fingerprint, now=instant)
            except ValueError:
                print('PASS rejected ' + label)
            else:
                raise AssertionError('Accepted ' + label)
        print('Fixtures: ./.runtime/fixtures.json')
    finally:
        request('DELETE', '/tokens/' + token['id'])


if __name__ == '__main__':
    try:
        main()
    except LocalConnectionError as error:
        raise SystemExit(str(error)) from None
