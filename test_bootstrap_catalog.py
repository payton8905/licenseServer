"""Verify readiness handling without contacting or modifying a license server."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch


def load_bootstrap():
    spec = importlib.util.spec_from_file_location('catalog_bootstrap_test', Path(__file__).with_name('bootstrap-catalog.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapCatalogTests(unittest.TestCase):
    def test_accepts_healthy_200_and_204_and_exports_the_trusted_ca(self):
        for status in (200, 204):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                module = load_bootstrap()
                module.RUNTIME = Path(directory)
                ca = MagicMock()
                ca.read_bytes.return_value = b'public-ca-fixture'
                response = MagicMock()
                response.__enter__.return_value.status = status
                product = types.ModuleType('product')
                product.admin = MagicMock()
                product.initialize = MagicMock(return_value={'product_id': 'existing-product'})
                product.complete_catalog = MagicMock(side_effect=lambda catalog: catalog)
                product.export_public = MagicMock()
                with patch.object(module, 'Path', return_value=ca), patch.object(module.ssl, 'create_default_context'), patch.object(module, 'local_open', return_value=response), patch.dict(sys.modules, {'product': product}):
                    module.main()
                self.assertEqual((module.RUNTIME / 'root.crt').read_bytes(), b'public-ca-fixture')
                product.export_public.assert_called_once_with({'product_id': 'existing-product'})

    def test_unhealthy_gateway_stops_before_provisioning(self):
        module = load_bootstrap()
        with tempfile.TemporaryDirectory() as directory:
            module.RUNTIME = Path(directory)
            response = MagicMock()
            response.__enter__.return_value.status = 503
            with patch.object(module.ssl, 'create_default_context'), patch.object(module, 'local_open', return_value=response), patch.object(module.time, 'monotonic', side_effect=[0, 181]):
                with self.assertRaisesRegex(SystemExit, 'readiness timed out'):
                    module.main()
            self.assertFalse((module.RUNTIME / 'root.crt').exists())


if __name__ == '__main__':
    unittest.main()
