#!/usr/bin/env python3
"""PoC client verifier for Keygen base64+ed25519 Machine Files (no API calls).

Requires Python cryptography. The public key must be obtained from a trusted
source and pinned; the expected fingerprint must come from the local device.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Missing signed expiry')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Expiry must include timezone')
    return result


def verify(certificate, public_key_hex, fingerprint, *, now=None):
    lines = certificate.strip().splitlines()
    if lines[0] != '-----BEGIN MACHINE FILE-----' or lines[-1] != '-----END MACHINE FILE-----':
        raise ValueError('Expected a MACHINE FILE')
    envelope = json.loads(base64.b64decode(''.join(lines[1:-1]), validate=True))
    if envelope.get('alg') != 'base64+ed25519':
        raise ValueError('Unsupported algorithm')
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex.strip()))
    try:
        key.verify(base64.b64decode(envelope['sig'], validate=True), ('machine/' + envelope['enc']).encode('ascii'))
    except InvalidSignature as exc:
        raise ValueError('Invalid signature') from exc
    document = json.loads(base64.b64decode(envelope['enc'], validate=True))
    now = now or datetime.now(timezone.utc)
    if now >= timestamp(document['meta'].get('expiry')):
        raise ValueError('Machine file expired')
    if now < timestamp(document['meta']['issued']):
        raise ValueError('Machine file was issued in the future')
    machine = document['data']
    if machine['type'] != 'machines' or machine['attributes']['fingerprint'] != fingerprint:
        raise ValueError('Device fingerprint mismatch')
    license_id = machine['relationships']['license']['data']['id']
    licenses = [item for item in document.get('included', []) if item['type'] == 'licenses' and item['id'] == license_id]
    if len(licenses) != 1:
        raise ValueError('Expected the related license in the signed file')
    license = licenses[0]
    if license['attributes'].get('suspended'):
        raise ValueError('License suspended')
    if now >= timestamp(license['attributes'].get('expiry')):
        raise ValueError('License expired')
    return document


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--fingerprint', required=True)
    args = parser.parse_args()
    try:
        result = verify(args.file.read_text(), args.public_key.read_text(), args.fingerprint)
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f'INVALID: {exc}')
    print('VALID: signed machine file, matching fingerprint, file and license not expired')
