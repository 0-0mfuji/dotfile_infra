#!/usr/bin/env python3
"""Render a token-bearing QR without putting the token in logs or arguments."""
import argparse
import ipaddress
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def mobile_url(base, token):
    parsed = urlsplit(base.strip())
    if parsed.scheme != 'http' or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Tailnet内のHTTP接続先を設定してください')
    address = ipaddress.ip_address(parsed.hostname or '')
    if address not in ipaddress.ip_network('100.64.0.0/10') or not parsed.port:
        raise ValueError('TailscaleのIPとポートが必要です')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', token):
        raise ValueError('NanoMuseの認証情報を確認してください')
    return base.strip().rstrip('/') + '/#token=' + token


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--png', action='store_true')
    args = parser.parse_args()
    root = Path.home()
    url = mobile_url((root / '.config/secretary/mobile-url').read_text(),
                     (root / '.nanomuse/server_token').read_text().strip())
    import qrcode
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    if args.png:
        qr.make_image(fill_color='black', back_color='white').save(sys.stdout.buffer, format='PNG')
    else:
        qr.print_ascii(out=sys.stdout, invert=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError):
        print('スマホ用QRを作れません。サーバーのTailnet接続先とNanoMuseの設定を確認してください。', file=sys.stderr)
        sys.exit(1)
