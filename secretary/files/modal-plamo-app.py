#!/usr/bin/env python3
"""Private Modal function for the pinned PLaMo model; no public web endpoint."""
import modal

MODEL = 'pfnet/plamo-3-translate-2b'
REVISION = 'cf66d22fbe6202c56b8e5d283691aa1da53d05af'
MODEL_PATH = '/models/plamo'


def download_model():
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL, revision=REVISION, local_dir=MODEL_PATH,
                      ignore_patterns=['*.gguf', '*.md', 'figures/*'])


image = (modal.Image.debian_slim(python_version='3.11')
         .pip_install('torch==2.8.0', 'transformers==4.57.1', 'accelerate==1.12.0',
                      'huggingface_hub==0.36.0', 'sentencepiece', 'numpy==2.3.5',
                      'numba==0.62.1')
         .run_function(download_model, timeout=1800))
app = modal.App('secretary-plamo-translation')


@app.cls(image=image, gpu=['A10', 'L4'], max_containers=1, scaledown_window=10, timeout=900)
class Translator:
    @modal.enter()
    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH, trust_remote_code=True, local_files_only=True,
            dtype=torch.bfloat16, device_map='cuda')

    @modal.method()
    def translate(self, text):
        return self._translate(text)

    @modal.method()
    def translate_batch(self, texts):
        if not isinstance(texts, list) or not 1 <= len(texts) <= 256:
            raise ValueError('batch must contain 1 to 256 texts')
        # A single remote call amortizes startup and network overhead. The client
        # performs document extraction and skips cached translations beforehand.
        return [self._translate(text) for text in texts]

    def _translate(self, text):
        import torch
        if not isinstance(text, str) or not text.strip():
            raise ValueError('text must be nonempty')
        if len(self.tokenizer.encode(text, add_special_tokens=False)) > 1536:
            raise ValueError('input exceeds 1536 tokens')
        inputs = self.tokenizer.apply_chat_template(
            [{'role': 'user', 'content': text}], source_lang='en', target_lang='ja',
            add_generation_prompt=True, return_dict=True, return_tensors='pt').to(self.model.device)
        with torch.inference_mode():
            output = self.model.generate(**inputs, do_sample=False, use_cache=True, max_new_tokens=3072)
        tokens = output[0, inputs['input_ids'].shape[1]:]
        eos = self.model.generation_config.eos_token_id
        if len(tokens) >= 3072 and int(tokens[-1]) not in (eos if isinstance(eos, list) else [eos]):
            raise RuntimeError('output limit reached')
        result = self.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        if not result:
            raise RuntimeError('empty translation')
        return {'text': result, 'model': MODEL, 'revision': REVISION,
                'gpu': torch.cuda.get_device_name(0)}
