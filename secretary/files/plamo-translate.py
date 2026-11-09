#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One invocation owns the model and releases all CUDA memory on exit. JSON stdin/out."""
import json
import os
import sys
import fcntl
from pathlib import Path


def translate(request, model_dir):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; CPU fallback is intentionally not automatic')
    # No downloading or remote API at inference time. Custom code was fixed at installation.
    tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_dir, trust_remote_code=True, local_files_only=True,
        dtype=torch.bfloat16, device_map='cuda',
    )
    text = request['text']
    options = {'target_lang': request.get('target_lang', 'ja'), 'add_generation_prompt': True,
               'return_dict': True, 'return_tensors': 'pt'}
    for key in ('source_lang', 'context', 'glossary', 'form'):
        if request.get(key):
            options[key] = request[key]
    # Bound each input in tokens, not characters. Paragraphs are preferred, oversized
    # paragraphs are split in tokenizer space. All chunks finish or the job fails.
    parts = []
    current = ''
    for paragraph in text.split('\n\n'):
        candidate = current + ('\n\n' if current else '') + paragraph
        if len(tokenizer.encode(candidate)) <= 1536:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ''
        tokens = tokenizer.encode(paragraph, add_special_tokens=False)
        for i in range(0, len(tokens), 1536):
            parts.append(tokenizer.decode(tokens[i:i + 1536], skip_special_tokens=True))
    if current:
        parts.append(current)
    translated = []
    for part in parts:
        inputs = tokenizer.apply_chat_template([{'role': 'user', 'content': part}], **options).to(model.device)
        if inputs['input_ids'].shape[1] > 4096:
            raise ValueError('context/glossary too large; reduce the request')
        with torch.inference_mode():
            output = model.generate(**inputs, do_sample=False, max_new_tokens=3072)
        generated = output[0, inputs['input_ids'].shape[1]:]
        eos = model.generation_config.eos_token_id
        eos_ids = eos if isinstance(eos, list) else [eos]
        if len(generated) >= 3072 and int(generated[-1]) not in eos_ids:
            raise RuntimeError('translation hit output limit; retry with smaller source chunks')
        translated.append(tokenizer.decode(generated, skip_special_tokens=True))
    return {'text': '\n\n'.join(translated), 'chunks': len(parts), 'local_inference': True}


if __name__ == '__main__':
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    with Path('/run/lock/secretary-plamo-model.lock').open('r') as model_lock:
        fcntl.flock(model_lock.fileno(), fcntl.LOCK_SH)
        request = json.load(sys.stdin)
        result = translate(request, '/var/lib/secretary-models/plamo-3-translate-2b')
        target = Path(request['output'])
        # Exclusive creation: never replace a source file or a previous translation.
        with target.open('x', encoding='utf-8') as stream:
            stream.write(result['text'])
    print(json.dumps({k: v for k, v in result.items() if k != 'text'}))
