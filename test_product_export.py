"""Verify the vendor/customer boundary without a running Keygen or private .env."""
import base64
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class PublicExportTests(unittest.TestCase):
    def test_project_quota_defaults_and_explicit_unlimited(self):
        smoke = types.ModuleType('smoke')
        poc = types.ModuleType('poc')
        poc.ROOT, poc.RUNTIME, poc.LocalConnectionError = Path('.'), Path('.'), RuntimeError
        spec = importlib.util.spec_from_file_location('quota_product_test', Path(__file__).parent/'product.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'smoke': smoke, 'poc': poc}):
            spec.loader.exec_module(module)
        self.assertEqual(module.project_quota({'max_projects':3}), 3)
        self.assertEqual(module.project_quota({'maxProjects':5}), 5)
        self.assertEqual(module.project_quota({'max_projects':3}, -1), -1)
        self.assertEqual(module.project_quota({'max_projects':3}, 10), 10)
        for value in [None,0,-2,True,False,1.5,'5',2147483648]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.project_quota({'max_projects':value})
        with self.assertRaises(ValueError):
            module.project_quota({})
        with self.assertRaises(ValueError):
            module.project_quota({'max_projects':3,'maxProjects':-1})

    def test_public_configuration_uses_shared_service_without_vendor_secrets(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            smoke = types.ModuleType('smoke')
            smoke.request = lambda *args: {'data': {'meta': {'keys': {
                'ed25519': base64.b64encode(b'a' * 64).decode()
            }}}}
            poc = types.ModuleType('poc')
            poc.ROOT, poc.RUNTIME = root, runtime
            poc.LocalConnectionError = RuntimeError
            spec = importlib.util.spec_from_file_location('vendor_product_export_test', root/'product.py')
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'smoke': smoke, 'poc': poc}):
                spec.loader.exec_module(module)
            with patch.dict(os.environ, {'LICENSE_PUBLIC_URL': 'https://licenses.example.com/'}):
                module.export_public({'account_id': 'account', 'product_id': 'product'})
            values = dict(line.split('=', 1) for line in (runtime/'product-public.env').read_text().splitlines())
            self.assertEqual(values, {
                'LICENSE_MODE': 'offline',
                'LICENSE_ACCOUNT_ID': 'account',
                'LICENSE_PRODUCT_ID': 'product',
                'LICENSE_PUBLIC_KEY': 'a' * 64,
                'LICENSE_API_URL': 'https://licenses.example.com',
            })


if __name__ == '__main__':
    unittest.main()
