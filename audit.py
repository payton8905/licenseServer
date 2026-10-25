#!/usr/bin/env python3
"""Exercise licensing against an isolated product DB and temporary Keygen product.

Requires the running vendor PoC and a built customer image. Optional --binary
mounts a freshly compiled Go API without rebuilding the full scanning image.
All customer test containers and temporary Keygen objects are removed on exit.
Private test state and a public results.json remain under .runtime/audit-*/.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import zipfile

import product
import smoke
from poc import RUNTIME


FEATURES = product.FEATURES


def docker(*args, **kwargs):
    result = subprocess.run(['docker', *map(str, args)], capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError('Docker operation failed: '+str(args[0])+': '+result.stderr.decode(errors='replace').strip()[:500])
    return result.stdout


class Audit:
    def __init__(self, image, binary):
        self.run_id = secrets.token_hex(4)
        self.root = RUNTIME / ('audit-'+self.run_id)
        self.root.mkdir(mode=0o700)
        self.image, self.binary = image, binary
        self.production = binary is None
        self.db = 'sbomscan-audit-db-'+self.run_id
        self.apps = {}
        self.tokens = {}
        self.results = []
        self.assertions = 0
        self.product_id = None
        self.owned_entitlements = []
        self.policies = {}
        self.entitlements = {}
        self.password = secrets.token_hex(24)

    def record(self, name):
        self.results.append({'name': name, 'status': 'PASS'})
        print('PASS', name, flush=True)

    def require(self, value, message):
        self.assertions += 1
        if not value:
            raise AssertionError(message)

    def sql(self, query, db='audit_a'):
        return docker('exec', '-i', self.db, 'psql', '-U', 'audit', '-d', db,
                      '-tA', '-v', 'ON_ERROR_STOP=1', input=query.encode()).decode().strip()

    def setup(self):
        self.baseline_products = {item['id'] for item in smoke.request('GET','/products?limit=100')['data']}
        env = self.root/'db.env'
        env.write_text('POSTGRES_USER=audit\nPOSTGRES_DB=audit_a\nPOSTGRES_PASSWORD='+self.password+'\n')
        env.chmod(0o600)
        docker('run', '-d', '--name', self.db, '--network', 'sbomscan-keygen-poc_default',
               '--env-file', env, '--tmpfs', '/var/lib/postgresql/data:rw', 'postgres:15-alpine')
        for _ in range(100):
            probe = subprocess.run(['docker', 'exec', self.db, 'pg_isready', '-h', '127.0.0.1', '-U', 'audit'], capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(.2)
        self.sql('CREATE DATABASE audit_b;')
        self.product_id = smoke.create('products', {'name': 'Temporary license audit '+self.run_id})['id']
        entitlements = smoke.request('GET', '/entitlements?limit=100')['data']
        for code in FEATURES:
            found = next((e for e in entitlements if e['attributes']['code'] == code), None)
            if found is None:
                found = smoke.create('entitlements', {'name': code, 'code': code})
                self.owned_entitlements.append(found['id'])
            self.entitlements[code] = found['id']
        for plan in ['Basic', 'Professional', 'Enterprise']:
            policy = smoke.create('policies', {
                'name': 'Audit '+plan, 'scheme': 'ED25519_SIGN', 'duration': 2592000,
                'strict': True, 'floating': True, 'protected': False,
                'maxMachines': 2, 'maxProcesses': 10, 'requireHeartbeat': False,
                'requireCheckIn': False, 'authenticationStrategy': 'MIXED',
            }, {'product': ('products', self.product_id)})
            self.policies[plan] = policy['id']
            self.set_features(plan, FEATURES)
        account = smoke.request('GET', '')['data']
        import base64
        self.public_key = base64.b64decode(account['meta']['keys']['ed25519']).decode()

    def set_features(self, plan, features):
        path = '/policies/'+self.policies[plan]+'/entitlements'
        existing = smoke.request('GET', path)['data']
        wanted = {self.entitlements[f] for f in features}
        current = {e['id'] for e in existing}
        for method, ids in [('DELETE', current-wanted), ('POST', wanted-current)]:
            if ids:
                smoke.request(method, path, {'data': [{'type': 'entitlements', 'id': eid} for eid in ids]})

    def stop(self, slot='a'):
        app = self.apps.pop(slot, None)
        if app:
            subprocess.run(['docker', 'rm', '-f', app['name']], capture_output=True)

    def start(self, profile, mode='offline', slot='a', db='audit_a', overrides=None, expect_start_failure=False):
        self.stop(slot)
        work = self.root/db
        for part in ['uploads', 'certs', 'backups', 'builds', 'state-'+profile]:
            (work/part).mkdir(parents=True, exist_ok=True)
        port = 0  # Docker selects an available loopback port (Windows reserves ranges).
        values = {
            'DATABASE_URL': f'postgres://audit:{self.password}@{self.db}:5432/{db}?sslmode=disable',
            'PORT': '8000', 'ADMIN_USERNAME': 'audit-admin', 'ADMIN_PASSWORD': self.password,
            'LICENSE_MODE': mode, 'LICENSE_ACCOUNT_ID': smoke.ENV['KEYGEN_ACCOUNT_ID'],
            'LICENSE_PRODUCT_ID': self.product_id, 'LICENSE_PUBLIC_KEY': self.public_key,
            'LICENSE_API_URL': 'https://keygen.localhost:8443', 'LICENSE_CA_FILE': '/trust/root.crt',
            'LICENSE_STATE_DIR': '/customer/state-'+profile, 'LICENSE_MACHINE_ID_PATH': '/host/machine-id',
            'UPLOAD_DIR': '/customer/uploads', 'CERT_DIR': '/customer/certs',
            'BACKUP_DIR': '/customer/backups', 'ANALYZER_BUILD_DIR': '/customer/builds',
            'LOG_FILE_PATH': '/customer/app.log', 'RESOLUTION_LAYER_ENABLED': 'false',
            'VULNERABILITY_PACKAGER_PATH': '/app/backend-assets/prepare-tracewolf-vulnerability-db.ps1',
        }
        values.update(overrides or {})
        env = self.root/('app-'+slot+'.env')
        env.write_text(''.join(f'{k}={v}\n' for k,v in values.items()))
        env.chmod(0o600)
        name = 'sbomscan-audit-api-'+self.run_id+'-'+slot
        uid = f'{os.getuid()}:{os.getgid()}' if hasattr(os, 'getuid') else '0:0'
        args = ['run', '-d', '--name', name, '--user', uid,
                '--network', 'sbomscan-keygen-poc_default', '-p', '127.0.0.1::8000',
                '--env-file', env, '-v', str(work.resolve())+':/customer',
                '-v', str((RUNTIME/'root.crt').resolve())+':/trust/root.crt:ro',
                '-v', '/etc/machine-id:/host/machine-id:ro',
                '-v', str((Path(os.environ['SBOMSCAN_SOURCE_DIR'])/'backend/app/assets').resolve())+':/app/backend-assets:ro']
        if self.binary:
            args += ['-v', str(self.binary.resolve())+':/audit-api:ro', '--entrypoint', '/audit-api']
        args.append(self.image)
        self.apps[slot] = {'name': name, 'port': port, 'state': work/('state-'+profile)/'state.json', 'db': db}
        docker(*args)
        if expect_start_failure:
            for _ in range(150):
                running = docker('inspect','--format','{{.State.Running}}',name).decode().strip()
                if running == 'false':
                    logs = docker('logs',name).decode(errors='replace')
                    # Structured application logs are written to app.log.
                    logs += (work/'app.log').read_text() if (work/'app.log').exists() else ''
                    self.require('development builds' in logs,'Production failed for a reason other than the disabled-mode guard')
                    self.stop(slot)
                    return
                time.sleep(.2)
            raise AssertionError('Production image allowed disabled licensing mode')
        binding = docker('port', name, '8000/tcp').decode().strip().splitlines()[0]
        port = int(binding.rsplit(':', 1)[1])
        self.apps[slot]['port'] = port
        for _ in range(150):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1).close()
                break
            except (OSError, urllib.error.URLError):
                time.sleep(.2)
        else:
            raise RuntimeError('Isolated API did not become healthy')
        if db not in self.tokens:
            self.tokens[db] = []
            # Represent an administrator who already changed the initial
            # password; startup correctly re-enforces a still-initial password.
            self.sql("UPDATE users SET password_hash='fixture-after-initial-change',must_change_password=FALSE,last_login_at=NOW() WHERE username='audit-admin';", db)
            for i in range(8):
                if i:
                    self.sql(f"INSERT INTO users(username,password_hash,role,is_active,must_change_password,last_login_at) VALUES('audit-user-{i}','fixture-only','analyst',TRUE,FALSE,NOW());", db)
                token = secrets.token_urlsafe(40)
                hashed = hashlib.sha256(token.encode()).hexdigest()
                self.sql(f"INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES({i+1},'{hashed}',NOW()+INTERVAL '1 hour');", db)
                self.tokens[db].append(token)

    def request(self, method, path, body=None, *, expected=200, slot='a', user=0, content_type=None):
        app = self.apps[slot]
        headers = {'Content-Type': content_type or 'application/json'}
        if user is not None:
            headers['Authorization'] = 'Bearer '+self.tokens[app['db']][user]
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f'http://127.0.0.1:{app["port"]}/api/'+path,
                                     method=method, headers=headers, data=data)
        try:
            response = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            self.require(response.status in ((expected,) if isinstance(expected, int) else expected),
                         f'{method} {path}: expected {expected}, got {response.status}')
            try:
                return json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                return raw

    def license(self, plan='Basic', seconds=86400, users=10, deployments=2, metadata=None):
        return smoke.create('licenses', {
            'name': 'Temporary audit '+self.run_id, 'expiry': (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(),
            'maxMachines': deployments, 'maxProcesses': users,
            'metadata': {'plan': plan, 'concurrent_users': users, 'max_projects': -1, **(metadata or {})},
        }, {'policy': ('policies', self.policies[plan])})

    def checkout(self, machine):
        return smoke.request('POST', '/machines/'+machine+'/actions/check-out?algorithm=base64%2Bed25519&include=license,license.entitlements&ttl=2592000')['data']['attributes']['certificate']

    def machine_file(self, license):
        fp = self.request('GET', 'license/status')['fingerprint']
        machine = smoke.create('machines', {'fingerprint': fp}, {'license': ('licenses', license['id'])})
        return machine['id'], self.checkout(machine['id'])

    def import_file(self, certificate, expected=200):
        return self.request('POST', 'license/import', certificate.encode(), expected=expected, content_type='text/plain')

    def multipart(self, filename, content):
        boundary = 'audit-'+secrets.token_hex(16)
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
        return body, 'multipart/form-data; boundary='+boundary

    def run(self):
        self.setup()
        self.start('initial')
        self.request('GET', 'auth/captcha', user=None)
        self.request('POST', 'auth/login', {}, user=None, expected=(400,422))
        self.request('POST', 'auth/register', {}, user=None, expected=403)
        self.request('GET', 'projects')
        for method, path in [('POST','projects'), ('PATCH','projects/1'), ('DELETE','projects/1'),
                             ('POST','scan/no-job'), ('POST','analyzer/builds'), ('POST','vulnerability-db/update')]:
            self.request(method, path, {}, expected=403)
        self.request('POST', 'license/import', b'forged', content_type='text/plain', expected=422)
        self.request('POST', 'license/import', b'forged', content_type='text/plain', user=1, expected=403)
        self.record('Unlicensed read-only, authentication entry points, admin-only recovery')

        for plan in ['Basic', 'Professional', 'Enterprise']:
            for mode in ['online', 'activation', 'offline']:
                self.start(plan+'-'+mode, mode)
                lic = self.license(plan)
                if mode == 'offline':
                    _, certificate = self.machine_file(lic)
                    state = self.import_file(certificate)
                else:
                    state = self.request('POST', 'license/activate', {'license_key': lic['attributes']['key']})
                self.require(not state['read_only'] and state['plan'] == plan and state['concurrent_users'] == 10,
                             'Plan, mode or quota not applied')
                self.request('POST', 'projects', {'name': plan+' '+mode, 'system_name': 'audit',
                             'system_version': '1', 'system_admin': 'audit'}, expected=201)
                self.request('POST', 'license/activate', {'license_key': lic['attributes']['key']}, expected=422 if mode=='offline' else 200)
                self.request('POST', 'license/refresh', expected=200 if mode=='online' else 422)
                if mode=='online':
                    self.request('POST','license/import',b'not enabled',content_type='text/plain',expected=422)
                self.record(plan+' / '+mode+' activation, quota, CRUD and mode boundaries')

        self.start('modules', 'offline')
        lic = self.license()
        machine, certificate = self.machine_file(lic)
        self.import_file(certificate)
        upload, content_type = self.multipart('baseline.cdx.json', b'{"bomFormat":"CycloneDX","specVersion":"1.5","components":[]}')
        job = self.request('POST','upload',upload,expected=201,content_type=content_type)['job_id']
        self.sql("UPDATE scan_jobs SET status='COMPLETE',finished_at=NOW(),progress=100 WHERE job_id='"+job+"';")
        self.job = job
        endpoints = [(FEATURES[0],'POST','scan/no-job',404),
                     (FEATURES[0],'PUT','projects/2147483000/tasks/2147483000/schedule',(400,404)),
                     (FEATURES[1],'POST','analyzer/verify-bundle',(400,422)),
                     (FEATURES[1],'GET','analyzer/records/2147483000/download',404),
                     (FEATURES[2],'PATCH','project-vulnerabilities/2147483000',404),
                     (FEATURES[3],'POST','vulnerability-db/import',400),
                     (FEATURES[3],'GET','vulnerability-db/offline-packager/windows',200)]
        for grants in [[], *[[feature] for feature in FEATURES], FEATURES]:
            self.set_features('Basic', grants)
            self.import_file(self.checkout(machine))
            self.require(set(self.request('GET','license/status')['features'])==set(grants),'Signed feature list mismatch')
            for feature, method, path, allowed_status in endpoints:
                self.request(method,path,{} if method!='GET' else None,expected=allowed_status if feature in grants else 403)
            self.request('GET','analyzer/records')
            self.request('GET','analyzer/builds')
            self.record('Feature gate matrix: '+(', '.join(grants) or 'no paid modules'))
        self.set_features('Basic',[FEATURES[0]])
        self.import_file(self.checkout(machine))
        bundle = io.BytesIO()
        with zipfile.ZipFile(bundle,'w') as archive:
            archive.writestr('tracewolf-analyzer-bundle.json','{}')
        data, ctype = self.multipart('bundle.zip',bundle.getvalue())
        before = self.sql('SELECT count(*) FROM scan_jobs;')
        self.request('POST','upload',data,content_type=ctype,expected=403)
        self.require(self.sql('SELECT count(*) FROM scan_jobs;')==before,'Collector bypass created a scan job')
        self.record('General upload cannot bypass the Collector entitlement')

        self.set_features('Basic',FEATURES)
        original = self.checkout(machine)
        self.import_file(original)
        self.import_file(original.replace('MACHINE FILE','LICENSE FILE'), expected=422)
        self.import_file(b'forged'.decode(), expected=422)
        self.require(not self.request('GET','license/status')['read_only'],'Invalid replacement removed valid license')
        self.start('copied')
        self.import_file(original, expected=422)
        self.start('wrong-key',overrides={'LICENSE_PUBLIC_KEY':secrets.token_hex(32)})
        self.import_file(original, expected=422)
        self.start('wrong-product',overrides={'LICENSE_PRODUCT_ID':'00000000-0000-0000-0000-000000000000'})
        self.import_file(original, expected=422)
        self.start('missing-config',overrides={'LICENSE_PRODUCT_ID':''})
        self.require(self.request('GET','license/status')['state']=='configuration_required','Missing config did not fail closed')
        self.record('Tampering, wrong file type, copied device, wrong key/product, missing trust settings')

        self.start('future')
        future = self.license(metadata={'not_before':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()})
        _, file = self.machine_file(future)
        self.import_file(file, expected=422)
        self.record('Signed start date rejects not-yet-valid license')

        self.start('short')
        short = self.license(seconds=10)
        short_machine, short_file = self.machine_file(short)
        self.import_file(short_file)
        time.sleep(11)
        self.require(self.request('GET','license/status')['read_only'],'Expired license stayed writable')
        self.readonly_exports()
        smoke.request('PATCH','/licenses/'+short['id'],{'data':{'type':'licenses','id':short['id'],'attributes':{'expiry':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}}})
        self.require(self.request('GET','license/status')['read_only'],'Offline renewal changed old file automatically')
        self.import_file(self.checkout(short_machine))
        self.require(not self.request('GET','license/status')['read_only'],'Offline renewed file did not restore access')
        self.record('Real expiry, JSON/SBOM/PDF export in read-only, and offline renewal')

        self.start('network', 'online')
        online = self.license()
        self.request('POST','license/activate',{'license_key':online['attributes']['key']})
        smoke.request('POST','/licenses/'+online['id']+'/actions/suspend')
        self.request('POST','license/refresh',expected=422)
        self.require(self.request('GET','license/status')['read_only'],'Suspension not enforced')
        self.readonly_exports()
        smoke.request('POST','/licenses/'+online['id']+'/actions/reinstate')
        self.request('POST','license/refresh')
        self.require(not self.request('GET','license/status')['read_only'],'Reinstatement not applied')
        self.record('Online central suspension and reinstatement')
        state_path = self.apps['a']['state']
        self.stop()
        state = json.loads(state_path.read_text())
        state['last_online'] = (datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
        state_path.write_text(json.dumps(state))
        self.start('network','online',overrides={'LICENSE_API_URL':'https://127.0.0.1:1'})
        self.require(self.request('GET','license/status')['state']=='grace','Network grace did not allow signed rights')
        self.stop()
        state['last_online'] = (datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()
        state_path.write_text(json.dumps(state))
        self.start('network','online',overrides={'LICENSE_API_URL':'https://127.0.0.1:1'})
        self.require(self.request('GET','license/status')['read_only'],'Network outage exceeded grace without restriction')
        self.record('Online disconnect within grace and beyond grace')
        self.start('network','offline',overrides={'LICENSE_API_URL':'https://127.0.0.1:1'})
        self.require(not self.request('GET','license/status')['read_only'],'Offline mode depended on online freshness')
        smoke.request('POST','/licenses/'+online['id']+'/actions/suspend')
        self.require(not self.request('GET','license/status')['read_only'],'Offline mode unexpectedly contacted server')
        self.record('Offline uses signed snapshot and cannot receive immediate central suspension')
        self.stop()
        state = json.loads(state_path.read_text())
        state['last_seen'] = (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
        state_path.write_text(json.dumps(state))
        self.start('network','offline')
        self.require(self.request('GET','license/status')['state']=='clock_error','Clock rollback was ignored')
        self.record('Persisted clock rollback detection')
        self.stop()
        state['last_seen'] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(state))
        smoke.request('DELETE','/licenses/'+online['id'])
        self.start('network','online')
        self.request('POST','license/refresh',expected=422)
        self.require(self.request('GET','license/status')['state']=='revoked','Deleted central license was not rejected')
        self.record('Online central license deletion is enforced')
        self.start('activation-disconnected','activation')
        activated = self.license()
        self.request('POST','license/activate',{'license_key':activated['attributes']['key']})
        self.start('activation-disconnected','activation',overrides={'LICENSE_API_URL':'https://127.0.0.1:1'})
        self.require(not self.request('GET','license/status')['read_only'],'First activation could not continue offline')
        self.record('First-activation mode survives restart without server connectivity')
        self.seats()

    def readonly_exports(self):
        self.request('GET','projects')
        self.request('GET','analyzer/records')
        self.request('POST','projects',{'name':'blocked'},expected=403)
        self.request('PATCH','projects/1',{'name':'blocked'},expected=403)
        self.request('DELETE','projects/1',expected=403)
        self.request('GET','download/'+self.job)
        self.request('GET','download/'+self.job+'/sbom')
        pdf = self.request('POST','download/'+self.job+'/pdf',{'language':'en'})
        self.require(isinstance(pdf,bytes) and pdf.startswith(b'%PDF-'),'PDF export did not produce a PDF')

    def seats(self):
        self.start('seats-a','activation')
        lic = self.license(users=2,deployments=2)
        key = lic['attributes']['key']
        self.request('POST','license/activate',{'license_key':key})
        self.sql('UPDATE auth_sessions SET license_seen_at=NULL;')
        self.request('POST','license/heartbeat',user=0)
        self.request('POST','license/heartbeat',user=1)
        self.request('POST','license/heartbeat',user=2,expected=429)
        self.start('seats-b','activation',slot='b',db='audit_b')
        self.request('POST','license/activate',{'license_key':key},slot='b')
        for user in [0,1]:
            self.request('POST','license/heartbeat',user=user,slot='b')
        self.request('POST','license/heartbeat',user=2,slot='b',expected=429)
        self.start('third','activation')
        self.request('POST','license/activate',{'license_key':key},expected=422)
        machines = smoke.request('GET','/licenses/'+lic['id']+'/machines')['data']
        self.require(len(machines)==2,'Failed third activation consumed another deployment slot')
        self.record('Two deployments allowed, third rejected, independent concurrent-user quotas')
        self.start('seats-a','activation')
        self.request('POST','auth/logout',user=1)
        self.request('POST','license/heartbeat',user=2)
        self.sql("UPDATE auth_sessions SET license_seen_at=NOW()-INTERVAL '91 seconds' WHERE user_id=3;")
        self.request('POST','license/heartbeat',user=3)
        self.sql('UPDATE users SET is_active=FALSE WHERE id=4;')
        self.request('POST','license/heartbeat',user=4)
        self.sql('UPDATE users SET is_active=TRUE WHERE id=4; UPDATE auth_sessions SET license_seen_at=NULL;')
        self.record('Seat release after logout, 90-second inactivity and account deactivation')
        # Return a newly generated session for user 2, whose old session logged out.
        token = secrets.token_urlsafe(40)
        self.tokens['audit_a'][1] = token
        hashed = hashlib.sha256(token.encode()).hexdigest()
        self.sql(f"INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES(2,'{hashed}',NOW()+INTERVAL '1 hour');")
        def compete(user):
            try:
                self.request('POST','license/heartbeat',user=user)
                return 200
            except AssertionError as error:
                if 'got 429' not in str(error):
                    raise
                return 429
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(compete,range(8)))
        self.require(codes.count(200)==2 and codes.count(429)==6,'Parallel requests overbooked seats')
        self.record('Eight concurrent users racing for two seats cannot overbook')
        self.sql('UPDATE auth_sessions SET license_seen_at=NULL;')
        extra = secrets.token_urlsafe(40)
        self.tokens['audit_a'][7] = extra
        hashed = hashlib.sha256(extra.encode()).hexdigest()
        self.sql(f"INSERT INTO auth_sessions(user_id,token_hash,expires_at) VALUES(1,'{hashed}',NOW()+INTERVAL '1 hour');")
        for user in [0,7,1]:
            self.request('POST','license/heartbeat',user=user)
        self.request('POST','license/heartbeat',user=2,expected=429)
        self.request('POST','auth/force-logout/2')
        self.request('POST','license/heartbeat',user=2)
        self.sql("UPDATE auth_sessions SET expires_at=NOW()-INTERVAL '1 second' WHERE user_id=3;")
        self.request('POST','license/heartbeat',user=3)
        self.record('Multiple sessions share one user seat; forced logout and session expiry release seats')
        if self.production:
            self.start('production-bypass','disabled',expect_start_failure=True)
            self.record('Production customer image rejects the disabled-mode bypass')
        else:
            self.start('development','disabled')
            self.require(not self.request('GET','license/status')['read_only'],'Explicit development mode not honored')
            self.record('Explicit disabled mode remains available in development binaries')
        self.start('mode-unspecified',overrides={'LICENSE_MODE':''})
        self.require(self.request('GET','license/status')['read_only'],'Unspecified mode disabled licensing')
        self.request('POST','projects',{'name':'must be denied'},expected=403)
        self.record('An unspecified mode fails closed instead of disabling licensing')
        self.project_quotas()

    def project_quotas(self):
        self.sql('CREATE DATABASE audit_quota;')
        self.start('project-quota', db='audit_quota')
        license = self.license(metadata={'max_projects': 3})
        machine, certificate = self.machine_file(license)
        self.import_file(certificate)
        state = self.request('GET', 'license/status')
        self.require(state['max_projects'] == 3 and state['project_count'] == 0, 'Signed project quota not exposed')
        def create(i):
            return self.request('POST', 'projects', {
                'name': 'quota-'+str(i), 'system_name': 'Quota', 'system_version': '1', 'system_admin': 'Audit',
                'max_projects': -1,  # A client payload must not override signed limits.
            }, expected=(201,409))
        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(create, range(20)))
        created = [item for item in outcomes if 'id' in item]
        self.require(len(created) == 3, 'Concurrent API requests exceeded project quota')
        self.require(all(item.get('code') == 'LICENSE_PROJECT_LIMIT' for item in outcomes if 'id' not in item), 'Quota error code missing')
        # Collector's second project-creation path must enforce the same quota.
        self.request('POST', 'analyzer/builds', {'project_mode': 'new', 'targets': ['linux-x64'],
            'project_name': 'collector-over-quota', 'party_a_name': 'Audit', 'contract_number': 'audit',
            'package_name': 'Audit package', 'package_version': '1', 'package_supplier': 'Audit'}, expected=409)
        self.require(self.request('GET','license/status')['project_count'] == 3, 'Collector created a project over quota')
        self.request('DELETE', 'projects/'+str(created[0]['id']), expected=204)
        replacement = create(100)
        self.require('id' in replacement, 'Deleting a project did not release quota')
        def update(limit):
            metadata = {k:v for k,v in license['attributes']['metadata'].items() if k not in ('max_projects','maxProjects')}
            metadata['max_projects'] = limit
            smoke.request('PATCH', '/licenses/'+license['id'], {'data': {'type':'licenses','id':license['id'], 'attributes': {'metadata':metadata}}})
        update(2)
        self.require(self.request('GET','license/status')['max_projects'] == 3, 'Offline grant changed without a new signed file')
        self.import_file(self.checkout(machine))
        self.require(len(self.request('GET','projects')) == 3, 'Downgrade removed existing projects')
        self.request('POST','projects',{'name':'downgrade-denied','system_name':'Audit','system_version':'1','system_admin':'Audit'},expected=409)
        update(-1)
        self.import_file(self.checkout(machine))
        for i in range(101,106):
            self.require('id' in create(i), 'Explicit unlimited quota failed')
        update(0)
        self.import_file(self.checkout(machine),expected=422)
        self.require(self.request('GET','license/status')['max_projects'] == -1, 'Invalid replacement overwrote valid grant')
        missing = self.license(metadata={'max_projects': None})
        self.start('quota-missing',db='audit_quota')
        _, legacy = self.machine_file(missing)
        self.import_file(legacy)
        self.request('POST','projects',{'name':'missing-denied','system_name':'Audit','system_version':'1','system_admin':'Audit'},expected=403)
        self.request('GET','projects')
        self.record('Signed project quotas: concurrent requests, Collector, client tampering, deletion, downgrade, unlimited and missing quota')
        online = self.license(metadata={'max_projects': 10})
        self.start('quota-online','online',db='audit_quota')
        self.request('POST','license/activate',{'license_key':online['attributes']['key']})
        metadata = {k:v for k,v in online['attributes']['metadata'].items() if k not in ('max_projects','maxProjects')}
        metadata['max_projects'] = 2
        smoke.request('PATCH','/licenses/'+online['id'],{'data':{'type':'licenses','id':online['id'],'attributes':{'metadata':metadata}}})
        self.request('POST','license/refresh')
        self.require(self.request('GET','license/status')['max_projects'] == 2, 'Online refresh did not update signed project quota')
        self.record('Online project quota changes apply after successful refresh')

    def cleanup(self):
        for slot in list(self.apps):
            self.stop(slot)
        subprocess.run(['docker','rm','-f',self.db],capture_output=True)
        if self.product_id:
            smoke.request('DELETE','/products/'+self.product_id)
            self.require(not smoke.request('GET','/products/'+self.product_id,expected=(200,404)).get('data'),'Temporary product still exists')
        if hasattr(self,'baseline_products'):
            remaining = {item['id'] for item in smoke.request('GET','/products?limit=100')['data']}
            self.require(self.baseline_products <= remaining,'An existing vendor product was removed')
        for eid in self.owned_entitlements:
            smoke.request('DELETE','/entitlements/'+eid)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='sbomscan-backend-go')
    parser.add_argument('--binary',type=Path)
    args = parser.parse_args()
    source = os.environ.get('SBOMSCAN_SOURCE_DIR')
    if not source or not (Path(source)/'backend/app/assets').is_dir():
        parser.error('Set SBOMSCAN_SOURCE_DIR to the SBOMScan checkout before running the integration audit')
    audit = Audit(args.image,args.binary)
    failure = None
    with product.admin():
        try:
            audit.run()
        except Exception as error:
            failure = str(error)
            audit.results.append({'name':'Audit workflow','status':'FAIL','detail':failure})
        finally:
            audit.cleanup()
            result = {'time':datetime.now(timezone.utc).isoformat(),'assertions':audit.assertions,
                      'results':audit.results,'passed':failure is None,'temporary_resources_removed':True,
                      'production_image_checked':audit.production}
            (audit.root/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('Results:',audit.root/'results.json',flush=True)
    if failure:
        raise SystemExit('FAILED: '+failure)
    print('ALL LICENSING AUDIT CHECKS PASSED',flush=True)
