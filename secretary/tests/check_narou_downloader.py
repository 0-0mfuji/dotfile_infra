"""Offline checks against the installed pinned dependency, not the live website."""
import argparse
import ast
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
from urllib.error import HTTPError
from unittest.mock import patch


def pagination(source):
    tree = ast.parse(source.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'narou_get_all_episodes')
    cases = [(100, 404, False, False), (200, 404, False, True),
             (None, 404, False, True), (100, 403, False, True), (100, 404, True, True)]
    for expected, code, first_error, should_raise in cases:
        class Parser:
            def feed(self, html):
                self.episodes = [(str(i), 'title', '') for i in range(100)]
                self._current_chapter = ''
        def fetch(url):
            if first_error or '?p=' in url:
                raise HTTPError(url, code, 'mock error', {}, None)
            return 'offline mock page'
        scope = {'HTTPError': HTTPError, 'NarouEpisodeListParser': Parser, 'narou_fetch': fetch,
                 'narou_get_novel_info_api': lambda _: ('title', 'author', '', {'episode_count': expected}),
                 '_sleep': lambda *_: None, '_emit_stage': lambda *_: None,
                 '_narou_series_from_html': lambda *_: ('', ''), 'print': lambda *_a, **_k: None}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<reviewed-pagination>', 'exec'), scope)
        raised = False
        try:
            result = scope[node.name]('https://ncode.syosetu.com/n0001aa/', 'n0001aa')
            assert len(result[3]) == 100
        except HTTPError:
            raised = True
        assert raised == should_raise, (expected, code, first_error)
    print('Pagination: 5 offline cases passed')


def partial_resume(source, text):
    spec = importlib.util.spec_from_file_location('checked_downloader', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    def denied(*_a, **_k):
        raise AssertionError('network access forbidden during offline validation')
    with patch('urllib.request.urlopen', denied), patch('urllib.request.OpenerDirector.open', denied):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            spec.loader.exec_module(module)
            sections, episodes = module._load_existing_txt(str(text))
    assert len(sections) == len(episodes) == 500, (len(sections), len(episodes))
    print('Existing partial TXT: 500 saved episodes recognized; resume starts at episode 501')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('downloader', type=Path)
    parser.add_argument('--partial-text', type=Path)
    args = parser.parse_args()
    pagination(args.downloader)
    if args.partial_text:
        partial_resume(args.downloader, args.partial_text)
