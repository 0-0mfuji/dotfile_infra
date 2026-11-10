#!/usr/bin/env python3
"""Private authenticated Modal RPC; JSON lines in and out, no public URL."""
import json
import sys
import modal


def main():
    translator = modal.Cls.from_name('secretary-plamo-translation', 'Translator')()
    for line in sys.stdin:
        try:
            request = json.loads(line)
            texts = request.get('texts', [request.get('text')])
            if not isinstance(texts, list) or not 1 <= len(texts) <= 256:
                raise ValueError('batch must contain 1 to 256 texts')
            if any(not isinstance(text, str) or not text.strip() or len(text) > 12000 for text in texts):
                raise ValueError('invalid text')
            result = (translator.translate_batch.remote(request['texts'])
                      if 'texts' in request else translator.translate.remote(request['text']))
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({'error': type(exc).__name__}), flush=True)


if __name__ == '__main__':
    main()
