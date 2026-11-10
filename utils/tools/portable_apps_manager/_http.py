"""Shared requests session that verifies TLS against the Windows certificate store.

Prerequisite: `truststore` (pip install truststore). On networks that re-sign HTTPS traffic with
a corporate root CA (installed in the Windows store, absent from certifi's bundle), plain
`requests` fails with CERTIFICATE_VERIFY_FAILED for many download hosts. truststore makes the
TLS check use the Windows store, like browsers and PowerShell do. It is scoped to this session
only (no global ssl patching), so other code in the same kernel is unaffected.
"""
import ssl

_session = None


class PrerequisiteError(RuntimeError):
    pass


def session():
    global _session
    if _session is None:
        try:
            import requests
            import truststore
        except ImportError as e:
            raise PrerequisiteError(f'Missing prerequisite "{e.name}" - run: pip install requests truststore') from None
        from requests.adapters import HTTPAdapter

        class _TruststoreAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs['ssl_context'] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                return super().init_poolmanager(*args, **kwargs)

            def proxy_manager_for(self, *args, **kwargs):
                kwargs['ssl_context'] = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                return super().proxy_manager_for(*args, **kwargs)

        s = requests.Session()
        s.mount('https://', _TruststoreAdapter())
        s.headers['User-Agent'] = 'portable-apps-updater'
        _session = s
    return _session
