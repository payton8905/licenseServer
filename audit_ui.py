#!/usr/bin/env python3
"""Browser regression for license-dependent controls, using mocked APIs only.

Run against a local instance of the newly built frontend. Requires Playwright
and Chromium. No request reaches a real product or license database.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def run(url):
    timestamp = '2026-10-18T12:00:00Z'
    state = {'mode':'offline','state':'active','read_only':False,'message':'License is valid',
             'fingerprint':'browser-audit-device','plan':'Basic','concurrent_users':10,'features':[]}
    project = {'id':1,'name':'既有專案','owner_user_id':1,'tasks':[
        {'id':1,'task_name':'既有任務','auto_scan_enabled':False,'created_at':timestamp}]}
    card = {'id':1,'project_id':1,'project_name':'既有專案','cve_id':'CVE-AUDIT-1',
            'status':'TODO','severity':'HIGH','title':'既有漏洞','created_at':timestamp,
            'updated_at':timestamp,'attachments':[],'updates':[]}
    board = {'project_id':1,'columns':[{'status':s,'cards':[card] if s=='TODO' else []}
             for s in ['TODO','IN_PROGRESS','BLOCKED','READY_FOR_VERIFY','DONE']]}
    writes = []
    errors = []
    results = []

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        if path=='/api/auth/me':
            value={'id':1,'username':'browser-admin','role':'admin','must_change_password':False}
        elif path.startswith('/api/license/'):
            value=dict(state)
        elif path=='/api/projects':
            value=[project]
        elif path=='/api/history':
            value=[{'job_id':status.lower(),'status':status,'project_id':1,'task_id':1,
                    'created_at':timestamp,'filename':status+'.cdx.json','target_type':'sbom_document'}
                   for status in ['READY','COMPLETE']]
        elif path=='/api/remediation-board' or path.endswith('/vulnerability-board'):
            value=board
        elif path=='/api/analyzer/records':
            value=[{'id':1,'project_name':'既有 Collector 紀錄','status':'complete',
                    'target_platform':'linux-x64','built_at':timestamp,
                    'download_url':'/api/analyzer/records/1/download'}]
        elif path=='/api/vulnerability-db':
            value={'enabled':False,'cron_expression':'0 3 * * *','update_stage':None,
                   'last_details':None,'last_run_at':None,'last_status':None}
        elif path.endswith('/schedule'):
            value=None
        elif path.endswith('/vulnerabilities'):
            value={'vulnerabilities':[]}
        elif path=='/api/system/status':
            value=None
        else:
            value=[]
        if request.method not in ['GET','HEAD'] and path not in ['/api/license/heartbeat','/api/client-logs']:
            writes.append((request.method,path))
        route.fulfill(status=200,content_type='application/json',body=json.dumps(value))

    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        def visit(tab):
            context=browser.new_context(viewport={'width':1440,'height':1000})
            context.add_init_script('localStorage.setItem("sbom_access_token","ui-audit-only");'
                                    'localStorage.setItem("app_language","zh-TW");'
                                    'localStorage.setItem("app_active_tab",'+json.dumps(tab)+');')
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('**/api/**',api)
            page.goto(url,wait_until='networkidle')
            return context,page

        def change(page,features,readonly=False):
            state.update(features=features,read_only=readonly,state='invalid' if readonly else 'active')
            page.evaluate("window.dispatchEvent(new Event('product-license-changed'))")

        context,page=visit('projects')
        add=page.get_by_role('button',name=re.compile('新增專案'))
        expect(add).to_be_enabled()
        expect(page.get_by_role('button',name=re.compile('匯入.*ZIP'))).to_be_disabled()
        add.click()
        expect(page.get_by_role('button',name=re.compile('一次完成'))).to_be_disabled()
        results.append('No-module license permits base CRUD but disables paid upload/import')
        context.close()

        context,page=visit('projects')
        page.get_by_text('既有專案',exact=True).first.click()
        page.evaluate("window.dispatchEvent(new CustomEvent('project-section',{detail:'tasks'}))")
        expect(page.get_by_role('button',name='建立掃描任務',exact=True)).to_be_disabled()
        page.evaluate("window.dispatchEvent(new CustomEvent('project-section',{detail:'overview'}))")
        expect(page.get_by_role('button',name='掃描',exact=True)).to_be_disabled()
        expect(page.get_by_role('button',name='新掃描',exact=True)).to_be_disabled()
        report=page.get_by_role('row').filter(has_text='COMPLETE.cdx.json').get_by_role('button',name='報告',exact=True)
        expect(report).to_be_enabled()
        change(page,['SBOMSCAN_SCAN'])
        expect(page.get_by_role('button',name='掃描',exact=True)).to_be_enabled()
        expect(page.get_by_role('button',name='新掃描',exact=True)).to_be_enabled()
        change(page,['SBOMSCAN_SCAN'],True)
        expect(page.get_by_role('button',name='掃描',exact=True)).to_be_disabled()
        expect(report).to_be_enabled()
        results.append('Scan/task/rescan controls obey entitlement and expiry; existing reports remain accessible')
        context.close()

        state.update(read_only=False,state='active',features=[])
        context,page=visit('analyzer')
        expect(page.get_by_text('既有 Collector 紀錄',exact=True)).to_be_visible()
        page.locator('select').first.select_option('1')
        build=page.get_by_role('button',name=re.compile('同時.*建置|建置.*雙|同時建立'))
        if build.count()==0:
            build=page.get_by_role('button',name=re.compile('Windows.*Linux|Linux.*Windows'))
        # Use the two per-platform build controls if the combined label changes.
        builds=page.get_by_role('button',name=re.compile('建置.*Windows|建置.*Linux|建立.*Windows|建立.*Linux'))
        assert builds.count()>=2,'Platform build controls were not found'
        expect(builds.first).to_be_disabled()
        expect(page.get_by_role('button',name='下載',exact=True).last).to_be_disabled()
        change(page,['SBOMSCAN_COLLECTOR'])
        expect(builds.first).to_be_enabled()
        expect(page.get_by_role('button',name='下載',exact=True).last).to_be_enabled()
        change(page,[],True)
        expect(builds.first).to_be_disabled()
        expect(page.get_by_text('既有 Collector 紀錄',exact=True)).to_be_visible()
        results.append('Collector build/download obey module and read-only state; history stays readable')
        context.close()

        state.update(read_only=False,state='active',features=[])
        context,page=visit('settings')
        page.get_by_role('button',name='漏洞資料庫',exact=True).first.click()
        for name in ['立即更新','下載 Windows 打包腳本','匯入離線資料庫','儲存排程']:
            expect(page.get_by_role('button',name=name,exact=True)).to_be_disabled()
        change(page,['SBOMSCAN_VULNDB_UPDATE'])
        expect(page.get_by_role('button',name='立即更新',exact=True)).to_be_enabled()
        change(page,['SBOMSCAN_VULNDB_UPDATE'],True)
        expect(page.get_by_role('button',name='立即更新',exact=True)).to_be_disabled()
        results.append('Vulnerability DB update/import/packager/schedule controls obey license')
        context.close()

        state.update(read_only=False,state='active',features=[])
        context,page=visit('remediation')
        page.get_by_text('CVE-AUDIT-1',exact=True).click()
        save=page.get_by_role('button',name='儲存變更',exact=True)
        expect(save).to_be_disabled()
        assert page.locator('[draggable=true]').count()==0
        change(page,['SBOMSCAN_REMEDIATION'])
        expect(save).to_be_enabled()
        change(page,['SBOMSCAN_REMEDIATION'],True)
        expect(save).to_be_disabled()
        results.append('Remediation remains viewable; edit and drag/drop require its licensed module')
        context.close()

        # Backward compatibility: an older API may return null for zero modules.
        state.update(read_only=False,state='active',features=None)
        context,page=visit('projects')
        expect(page.get_by_role('button',name=re.compile('新增專案'))).to_be_enabled()
        assert not errors,errors
        assert not writes,writes
        results.append('No unauthorized writes or JavaScript errors, including legacy null feature list')
        context.close()
        browser.close()
    for result in results:
        print('PASS',result,flush=True)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:13300')
    args=parser.parse_args()
    results=run(args.url)
    destination=Path(__file__).resolve().parent/'.runtime/license-audit-ui-results.json'
    destination.write_text(json.dumps({'passed':True,'scenarios':results},ensure_ascii=False,indent=2))
