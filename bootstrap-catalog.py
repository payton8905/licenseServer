"""Initialize the product catalog after the gateway is ready; preserve edits."""
from pathlib import Path
import os
import ssl
import time

from poc import RUNTIME, local_open


def main():
    if os.environ.get('LICENSE_BOOTSTRAP_CATALOG', 'true').strip().lower() == 'false':
        print('Automatic product catalog creation is disabled; create products and policies in the portal.', flush=True)
        return
    RUNTIME.mkdir(exist_ok=True)
    ca = Path('/caddy-data/caddy/pki/authorities/local/root.crt')
    deadline = time.monotonic() + 180
    print('Waiting for the local HTTPS gateway...', flush=True)
    while True:
        try:
            context = ssl.create_default_context(cafile=str(ca))
            with local_open('https://localhost:8443/v1/health', context=context, timeout=5) as response:
                if response.status not in (200, 204):
                    raise RuntimeError('API is not healthy')
            break
        except (OSError, RuntimeError):
            if time.monotonic() >= deadline:
                raise SystemExit('Gateway readiness timed out. Check gateway and web logs.') from None
            time.sleep(1)
    (RUNTIME / 'root.crt').write_bytes(ca.read_bytes())
    # smoke/product load the trusted CA at import time.
    import product
    with product.admin():
        catalog = product.complete_catalog(product.initialize())
        product.export_public(catalog)
    print('LicenseServer is ready: https://localhost:8443', flush=True)


if __name__ == '__main__':
    main()
