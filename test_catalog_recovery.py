import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


def load_product(directory):
    smoke = types.ModuleType('smoke')
    smoke.ENV = {'KEYGEN_ACCOUNT_ID': 'account'}
    smoke.BASE = 'https://localhost:8443/v1/accounts/account'
    smoke.create = MagicMock(side_effect=AssertionError('Must not create replacement objects'))
    smoke.private_json = lambda path, value: path.write_text(json.dumps(value))
    poc = types.ModuleType('poc')
    poc.ROOT = poc.RUNTIME = Path(directory)
    poc.LocalConnectionError = RuntimeError
    spec = importlib.util.spec_from_file_location('recovered_product_test', Path(__file__).with_name('product.py'))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'smoke': smoke, 'poc': poc}):
        spec.loader.exec_module(module)
    return module, smoke


class CatalogRecoveryTests(unittest.TestCase):
    def test_missing_local_file_reuses_existing_product_and_policies(self):
        with tempfile.TemporaryDirectory() as directory:
            module, smoke = load_product(directory)
            responses = {
                '/products': {'data': [{'id': 'existing-product', 'attributes': {'name': 'SBOMScan'}}]},
                '/products/existing-product/policies': {'data': [
                    {'id': tier, 'attributes': {'name': 'SBOMScan '+tier+' (evaluation)'}} for tier in module.PLANS
                ]},
                '/entitlements': {'data': [{'id': 'scan', 'attributes': {'code': 'SBOMSCAN_SCAN'}}]},
            }
            smoke.request = lambda method, path: responses[path]
            catalog = module.initialize()
            self.assertEqual(catalog['product_id'], 'existing-product')
            self.assertEqual(catalog['policies']['Basic'], 'Basic')
            self.assertEqual(catalog['pending_policy_entitlements'], [])
            self.assertEqual(catalog['deployment_model_version'], 3)
            self.assertTrue(module.CATALOG.exists())
            smoke.create.assert_not_called()

    def test_ambiguous_existing_products_are_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            module, smoke = load_product(directory)
            smoke.request = lambda *args: {'data': [{'id': str(i), 'attributes': {'name': 'SBOMScan'}} for i in (1, 2)]}
            with self.assertRaisesRegex(ValueError, 'Multiple SBOMScan'):
                module.initialize()
            smoke.create.assert_not_called()

    def test_pagination_follows_only_the_configured_account(self):
        with tempfile.TemporaryDirectory() as directory:
            module, smoke = load_product(directory)
            smoke.request = MagicMock(side_effect=[
                {'data': [1], 'links': {'next': smoke.BASE+'/products?page=2'}},
                {'data': [2]},
            ])
            self.assertEqual(module.list_resources('/products'), [1, 2])
            smoke.request = lambda *args: {'data': [], 'links': {'next': 'https://other.example/products'}}
            with self.assertRaisesRegex(RuntimeError, 'another server or account'):
                module.list_resources('/products')


if __name__ == '__main__':
    unittest.main()
