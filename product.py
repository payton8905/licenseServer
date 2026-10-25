#!/usr/bin/env python3
"""Vendor-side SBOMScan catalog/issuance using the existing Keygen CE API.

Run on the license-management host only. Never ship this directory or its .env
to a customer. Customer images contain only the public trust configuration.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import smoke
from poc import ROOT, RUNTIME, LocalConnectionError

FEATURES = ['SBOMSCAN_SCAN', 'SBOMSCAN_COLLECTOR', 'SBOMSCAN_REMEDIATION', 'SBOMSCAN_VULNDB_UPDATE']
PLANS = ['Trial', 'Basic', 'Professional', 'Enterprise']
PROJECT_DEFAULTS = {'Trial': 3, 'Basic': 5}
CATALOG = RUNTIME / 'product-catalog.json'


@contextmanager
def admin():
    credentials = base64.b64encode((smoke.ENV['KEYGEN_ADMIN_EMAIL'] + ':' + smoke.ENV['KEYGEN_ADMIN_PASSWORD']).encode()).decode()
    token = smoke.request('POST', '/tokens', {'data': {'type': 'tokens', 'attributes': {
        'name': 'SBOMScan vendor provisioning', 'expiry': (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
    }}}, auth='Basic '+credentials)['data']
    smoke.TOKEN = token['attributes']['token']
    try:
        yield
    finally:
        smoke.request('DELETE', '/tokens/'+token['id'])
        smoke.TOKEN = None


def initialize():
    catalog = None
    if CATALOG.exists():
        catalog = json.loads(CATALOG.read_text())
        if catalog['account_id'] != smoke.ENV['KEYGEN_ACCOUNT_ID']:
            raise ValueError('product-catalog.json 的 Account ID 與目前 Keygen 不同，請先確認管理端帳戶及設定檔，勿混用不同帳戶的產品目錄。')
        existing = smoke.request('GET', '/products/'+catalog['product_id'], expected=(200, 404))
        if existing.get('data'):
            return catalog
        # The local file is a mapping, not evidence that API objects still
        # exist. Keep a private recovery record before replacing stale IDs.
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = RUNTIME / ('product-catalog.stale-'+stamp+'.json')
        smoke.private_json(backup, catalog)
        print('舊產品已不存在於 Keygen；保留原目錄：', backup)
        print('重新建立 SBOMScan 產品與評估方案；既有客戶設定需改用新的 Product ID。')
    product = smoke.create('products', {'name': 'SBOMScan', 'metadata': {'commercial_plans_finalized': False}})
    catalog = {'product_id': product['id'], 'account_id': smoke.ENV['KEYGEN_ACCOUNT_ID'], 'policies': {},
               'entitlements': dict(catalog.get('entitlements', {})) if catalog else {}}
    # Save each successful step so retrying does not duplicate objects.
    smoke.private_json(CATALOG, catalog)
    return catalog


def complete_catalog(catalog):
    # Seed entitlements only when creating a policy. Subsequent issuance must
    # preserve the vendor's edits in Portal, including intentionally removed
    # paid modules. Track interrupted initialization separately for safe retry.
    pending = catalog.setdefault('pending_policy_entitlements', [])
    for feature in FEATURES:
        if feature in catalog['entitlements']:
            existing = smoke.request('GET', '/entitlements/'+catalog['entitlements'][feature], expected=(200, 404))
            if not existing.get('data'):
                del catalog['entitlements'][feature]
                smoke.private_json(CATALOG, catalog)
        if feature not in catalog['entitlements']:
            ent = smoke.create('entitlements', {'name': feature, 'code': feature})
            catalog['entitlements'][feature] = ent['id']
            smoke.private_json(CATALOG, catalog)
    for tier in PLANS:
        if tier in catalog['policies']:
            existing = smoke.request('GET', '/policies/'+catalog['policies'][tier], expected=(200, 404))
            if not existing.get('data'):
                del catalog['policies'][tier]
                smoke.private_json(CATALOG, catalog)
        if tier not in catalog['policies']:
            policy = smoke.create('policies', {
                'name': 'SBOMScan '+tier+' (evaluation)', 'duration': 2592000, 'scheme': 'ED25519_SIGN',
                # Keygen requires floating=true for a license with multiple
                # activated machines. Heartbeat/check-in are not required:
                # these are persistent deployment slots, not user sessions.
                'strict': True, 'floating': True, 'protected': False, 'maxMachines': 1, 'maxProcesses': 2,
                'requireHeartbeat': False, 'requireCheckIn': False,
                'authenticationStrategy': 'MIXED',
                'metadata': {'commercial_plan_finalized': False, 'concurrent_scope': 'per_deployment',
                             **({'max_projects': PROJECT_DEFAULTS[tier]} if tier in PROJECT_DEFAULTS else {})},
            }, {'product': ('products', catalog['product_id'])})
            catalog['policies'][tier] = policy['id']
            if tier not in pending:
                pending.append(tier)
            smoke.private_json(CATALOG, catalog)
        if tier in PROJECT_DEFAULTS:
            current = smoke.request('GET', '/policies/'+catalog['policies'][tier])['data']
            metadata = current['attributes'].get('metadata') or {}
            if 'max_projects' not in metadata and 'maxProjects' not in metadata:
                smoke.request('PATCH', '/policies/'+current['id'], {'data': {
                    'type': 'policies', 'id': current['id'],
                    'attributes': {'metadata': {**metadata, 'max_projects': PROJECT_DEFAULTS[tier]}},
                }})
        if tier not in pending:
            continue
        attached = smoke.request('GET', '/policies/'+catalog['policies'][tier]+'/entitlements')['data']
        attached_ids = {item['id'] for item in attached}
        missing = [eid for eid in catalog['entitlements'].values() if eid not in attached_ids]
        if missing:
            smoke.request('POST', '/policies/'+catalog['policies'][tier]+'/entitlements',
                          {'data': [{'type': 'entitlements', 'id': eid} for eid in missing]})
        pending.remove(tier)
        smoke.private_json(CATALOG, catalog)
    migrate_deployment_policies(catalog)
    return catalog


def migrate_deployment_policies(catalog):
    """One-time correction of the original single-machine evaluation setup.

    Preserve entitlements, quotas and all other vendor edits. After this
    migration, init/issue never force an existing policy back to floating.
    """
    if catalog.get('deployment_model_version', 1) >= 3:
        return
    for policy_id in catalog['policies'].values():
        policy = smoke.request('GET', '/policies/'+policy_id)['data']
        attributes = policy['attributes']
        metadata = attributes.get('metadata') or {}
        finalized = metadata.get('commercial_plan_finalized', metadata.get('commercialPlanFinalized'))
        scope = metadata.get('concurrent_scope', metadata.get('concurrentScope'))
        if (attributes.get('floating') is False
                and finalized is False and scope == 'per_deployment'):
            smoke.request('PATCH', '/policies/'+policy_id, {'data': {
                'type': 'policies', 'id': policy_id, 'attributes': {'floating': True},
            }})
    catalog['deployment_model_version'] = 3
    smoke.private_json(CATALOG, catalog)


def export_public(catalog):
    account = smoke.request('GET', '')['data']
    key = base64.b64decode(account['meta']['keys']['ed25519'], validate=True).decode('ascii')
    # This contains no admin token, password, license key, or signing private key.
    values = {
        'LICENSE_MODE': 'offline', 'LICENSE_ACCOUNT_ID': catalog['account_id'],
        'LICENSE_PRODUCT_ID': catalog['product_id'], 'LICENSE_PUBLIC_KEY': key,
        'LICENSE_API_URL': os.environ.get('LICENSE_PUBLIC_URL', 'https://localhost:8443').rstrip('/'),
    }
    (RUNTIME/'product-public.env').write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
    print('SBOMScan product:', catalog['product_id'])
    print('Portal Products: '+values['LICENSE_API_URL']+'/'+catalog['account_id']+'/app/products')
    print('Public trust configuration: ./.runtime/product-public.env')


def project_quota(metadata, override=None):
    """Resolve defaults when issuing; the resulting value belongs to the License."""
    if override is not None:
        value = override
    else:
        if 'max_projects' in metadata and 'maxProjects' in metadata and metadata['max_projects'] != metadata['maxProjects']:
            raise ValueError('Conflicting max_projects policy defaults')
        value = metadata.get('max_projects', metadata.get('maxProjects'))
    if type(value) is not int or (value != -1 and not 1 <= value <= 2147483647):
        raise ValueError('Project quota is required: set policy metadata.max_projects or --max-projects to a positive integer or -1 (unlimited)')
    return value


def issue(catalog, args):
    expiry = datetime.fromisoformat(args.expires.replace('Z','+00:00'))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError('--expires must be a future ISO8601 datetime including timezone')
    if args.not_before:
        start = datetime.fromisoformat(args.not_before.replace('Z','+00:00'))
        if start.tzinfo is None or start >= expiry:
            raise ValueError('--not-before must precede expiry and include timezone')
    if args.deployments < 1 or args.concurrent_users < 1:
        raise ValueError('Deployment and concurrent-user limits must be positive')
    policy_id = catalog['policies'][args.plan]
    policy = smoke.request('GET', '/policies/'+policy_id)['data']
    max_projects = project_quota(policy['attributes'].get('metadata') or {}, getattr(args, 'max_projects', None))
    if args.deployments > 1 and not policy['attributes']['floating']:
        raise ValueError(
            '此方案在 Keygen 設為 non-floating，只允許 1 台設備。'
            '若需多套部署，請在 Portal 將該 Policy 的 floating 設為 true；'
            '離線部署應保持 requireHeartbeat／requireCheckIn 關閉。'
        )
    users = smoke.request('GET','/users?email='+__import__('urllib.parse',fromlist=['quote']).quote(args.customer))['data']
    customer = next((u for u in users if u['attributes']['email'] == args.customer),None)
    if customer is None:
        customer = smoke.create('users', {'email':args.customer, 'role':'user'})
    metadata = {'plan': args.plan, 'concurrent_users': args.concurrent_users, 'concurrent_scope': 'per_deployment', 'max_projects': max_projects}
    if args.not_before:
        metadata['not_before'] = args.not_before
    license = smoke.create('licenses', {
        'name': 'SBOMScan '+args.plan+' — '+args.customer, 'expiry':expiry.isoformat(),
        'maxMachines':args.deployments, 'maxProcesses':args.concurrent_users, 'metadata':metadata,
    }, {'policy':('policies',policy_id),'owner':('users',customer['id'])})
    output = {'license_id':license['id'],'license_key':license['attributes']['key'], 'customer':args.customer,
              'product_id':catalog['product_id'],'expires':expiry.isoformat(), 'concurrent_users':args.concurrent_users, 'max_projects': max_projects}
    if args.fingerprint:
        machine = smoke.create('machines', {'name':'SBOMScan customer installation','fingerprint':args.fingerprint},
                               {'license':('licenses',license['id'])})
        ttl = max(3600, int((expiry-datetime.now(timezone.utc)).total_seconds()))
        result = smoke.request('POST','/machines/'+machine['id']+'/actions/check-out?algorithm=base64%2Bed25519&include=license,license.entitlements,license.policy&ttl='+str(ttl))
        certificate = result['data']['attributes']['certificate']
        path = RUNTIME/(license['id']+'.lic')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:
            f.write(certificate)
        output['machine_file'] = str(path)
    path = RUNTIME/(license['id']+'.json')
    smoke.private_json(path,output)
    print('Issued license:',license['id'])
    print('Private delivery record:',path)
    if args.fingerprint:
        print('Customer machine file:',output['machine_file'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    issuer=sub.add_parser('issue')
    issuer.add_argument('--customer',required=True)
    issuer.add_argument('--plan',choices=PLANS,required=True)
    issuer.add_argument('--expires',required=True)
    issuer.add_argument('--not-before')
    issuer.add_argument('--deployments',type=int,required=True)
    issuer.add_argument('--concurrent-users',type=int,required=True)
    issuer.add_argument('--max-projects',type=int,help='Positive project limit or -1 for unlimited; defaults to the policy metadata')
    issuer.add_argument('--fingerprint',help='Omit for online activation; set for fully offline delivery')
    args=parser.parse_args()
    try:
        with admin():
            catalog=complete_catalog(initialize())
            export_public(catalog)
            if args.command=='issue':
                issue(catalog,args)
    except (LocalConnectionError, ValueError, RuntimeError) as error:
        parser.exit(1, str(error)+'\n')
