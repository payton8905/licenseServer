#!/usr/bin/env python3
"""Local Keygen CE + official Portal; standard-library-only launcher."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / '.runtime'
COMPOSE_VERSION = 'v2.29.7'


class LocalConnectionError(RuntimeError):
    """The local license server is unreachable before an API response."""


def local_open(request, *, context, timeout=30):
    # These tools connect to the loopback-only PoC. Do not send administrator
    # credentials to an HTTP(S) proxy configured in the user's shell.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
    )
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError:
        raise  # Preserve real API responses such as 401, 403, and 422.
    except (urllib.error.URLError, OSError) as error:
        reason = getattr(error, 'reason', error)
        raise LocalConnectionError(
            '無法連線本機 Keygen HTTPS 服務（localhost:8443）：'
            f'{reason}\n'
            '請先執行 python3 ./poc.py check。\n'
            '若仍無法連線，執行 python3 ./poc.py restart，'
            '重建此 PoC 的容器與網路（保留資料 volumes），再重試原命令。'
        ) from error


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def compose(*args, **kwargs):
    return run([str(RUNTIME / 'docker-compose'), '-f', str(ROOT / 'compose.yaml'), *args], **kwargs)


def prepare_environment():
    """Create persistent credentials without requiring host Python dependencies."""
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    env = ROOT / '.env'
    if env.exists():
        return
    values = {
        'KEYGEN_EDITION': 'CE', 'KEYGEN_MODE': 'singleplayer',
        'KEYGEN_HOST': 'api.keygen.localhost', 'KEYGEN_DOMAIN': 'keygen.localhost',
        'KEYGEN_SUBDOMAIN': 'api', 'KEYGEN_PORTAL_HOST': 'localhost:8443',
        'KEYGEN_ACCOUNT_ID': str(uuid.uuid4()),
        'KEYGEN_ADMIN_EMAIL': os.environ.get('KEYGEN_ADMIN_EMAIL', 'admin@example.com'),
        'KEYGEN_ADMIN_PASSWORD': os.environ.get('KEYGEN_ADMIN_PASSWORD', 'admin123'),
        'POSTGRES_PASSWORD': secrets.token_hex(24),
        'SECRET_KEY_BASE': secrets.token_hex(64),
        'ENCRYPTION_DETERMINISTIC_KEY': base64.b64encode(secrets.token_bytes(32)).decode(),
        'ENCRYPTION_PRIMARY_KEY': base64.b64encode(secrets.token_bytes(32)).decode(),
        'ENCRYPTION_KEY_DERIVATION_SALT': base64.b64encode(secrets.token_bytes(32)).decode(),
        'RAILS_ENV': 'production', 'RAILS_LOG_TO_STDOUT': '1',
        'RAILS_MAX_THREADS': '2', 'WEB_CONCURRENCY': '1', 'SIDEKIQ_CONCURRENCY': '10',
        'NO_SENDGRID': '1',
    }
    fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out:
        out.write(''.join(f'{k}={v}\n' for k, v in values.items()))


def prepare():
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    binary = RUNTIME / 'docker-compose'
    if not binary.exists():
        import platform
        arch = {'x86_64': 'x86_64', 'aarch64': 'aarch64'}[platform.machine()]
        name = f'docker-compose-linux-{arch}'
        url = f'https://github.com/docker/compose/releases/download/{COMPOSE_VERSION}/{name}'
        payload = urllib.request.urlopen(url, timeout=120).read()
        expected = urllib.request.urlopen(url + '.sha256', timeout=30).read().decode().split()[0]
        if hashlib.sha256(payload).hexdigest() != expected:
            raise RuntimeError('Compose checksum mismatch')
        binary.write_bytes(payload)
        binary.chmod(0o755)
    prepare_environment()


def up():
    prepare()
    compose('up', '-d')
    compose('wait', 'catalog')
    print('Portal: https://localhost:8443\nCredentials: ./.env\nLocal CA: ./.runtime/root.crt')


def check():
    context = ssl.create_default_context(cafile=str(RUNTIME / 'root.crt'))
    for path in ['/', '/v1/ping', '/v1/health']:
        with local_open('https://localhost:8443' + path, context=context, timeout=10) as response:
            assert response.status in (200, 204), (path, response.status)
            print(f'PASS {path}: {response.status}')


def restart():
    # A plain container restart retains a broken bridge after some host/VM
    # network changes. Recreate only this stack; never remove its data volumes
    # or rerun the schema-loading setup task against an existing database.
    compose('down')
    compose('up', '-d')
    compose('wait', 'catalog')
    cert = compose('exec', '-T', 'gateway', 'cat', '/data/caddy/pki/authorities/local/root.crt', capture_output=True)
    (RUNTIME / 'root.crt').write_bytes(cert.stdout)
    check()


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'up'
    if command == 'up':
        up()
        check()
    elif command == 'check':
        check()
    elif command == 'restart':
        restart()
    elif command == 'down':
        compose('down')  # Retain all database volumes.
    elif command == 'status':
        compose('ps')
    elif command == 'logs':
        compose('logs', '--tail', '80', 'web', 'worker', 'gateway')
    else:
        raise SystemExit('Usage: python3 poc.py [up|check|restart|down|status|logs]')


if __name__ == '__main__':
    try:
        main()
    except LocalConnectionError as error:
        raise SystemExit(str(error)) from None
