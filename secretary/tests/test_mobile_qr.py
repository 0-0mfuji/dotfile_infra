import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('mobile', Path(__file__).parents[1] / 'files/nanomuse-mobile.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MobileTests(unittest.TestCase):
    def test_token_is_only_in_fragment(self):
        self.assertEqual(m.mobile_url('http://100.64.0.1:8787/', 'fixture-token'),
                         'http://100.64.0.1:8787/#token=fixture-token')

    def test_rejects_public_urls_credentials_and_invalid_tokens(self):
        for base in ('http://8.8.8.8:8787', 'http://127.0.0.1:8787',
                     'http://user:password@100.64.0.1:8787',
                     'http://100.64.0.1:8787/?token=old', 'http://100.64.0.1:8787/#old'):
            with self.assertRaises(ValueError):
                m.mobile_url(base, 'fixture-token')
        with self.assertRaises(ValueError) as error:
            m.mobile_url('http://100.64.0.1:8787', 'private invalid token')
        self.assertNotIn('private invalid token', str(error.exception))
