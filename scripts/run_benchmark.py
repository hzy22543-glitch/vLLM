"""Run one explicit APC condition using vLLM 0.31.0's official benchmark."""
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


def request_json(base, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=body, headers={'Content-Type': 'application/json'})
    # Loopback traffic must not depend on an inherited HTTP proxy.
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=180) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'HTTP {e.code} from {path}: {detail}') from e
    return json.loads(raw) if raw else {}



def warmup_prompt(tokenizer, index, max_model_len, output_tokens=64):
    # Count the actual chat template, not characters or repeated words.
    budget = min(2048, max_model_len - output_tokens)
    repeats = 2000
    while repeats > 0:
        prompt = f'Service warmup {index}. ' + ' warmup' * repeats
        ids = tokenizer.apply_chat_template(
            [{'role': 'user', 'content': prompt}], tokenize=True, add_generation_prompt=True)
        if hasattr(ids, 'keys'):
            ids = ids['input_ids']
        if len(ids) <= budget:
            return prompt
        repeats //= 2
    raise ValueError('Context limit is too small for the warmup and requested output')


def reset_cache(base):
    result = request_json(base, '/reset_prefix_cache', {})
    if result.get('success') is not True:
        raise RuntimeError(f'Cache reset did not succeed: {result}; stop without measuring')


def command(args, dataset, count, out):
    return [str(Path(sys.executable).with_name('vllm')), 'bench', 'serve',
            '--backend', 'openai-chat', '--endpoint', '/v1/chat/completions',
            '--base-url', args.base_url, '--model', args.model,
            '--tokenizer', args.model, '--dataset-name', 'custom',
            '--dataset-path', str(dataset), '--custom-output-len', '-1', '--skip-chat-template',
            '--disable-shuffle', '--no-oversample', '--num-prompts', str(count),
            '--max-concurrency', str(args.concurrency), '--request-rate', str(args.request_rate),
            '--seed', str(args.seed), '--temperature', '0', '--ignore-eos',
            '--num-warmups', '0', '--ready-check-timeout-sec', '0',
            '--save-result', '--save-detailed', '--percentile-metrics', 'ttft,tpot,itl,e2el',
            '--metric-percentiles', '50,95,99', '--result-dir', str(out),
            '--result-filename', 'result.json']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model', required=True, help='Local model/tokenizer directory')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--apc', choices=['off', 'on'], required=True)
    parser.add_argument('--cache-state', choices=['cold', 'hot'], required=True)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--request-rate', default='inf')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--warmups', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=1800)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip('/')
    if args.concurrency < 1 or args.warmups < 0 or args.timeout <= 0:
        parser.error('Invalid concurrency, warmups or timeout')
    dataset = args.dataset.resolve()
    records = [json.loads(x) for x in dataset.read_text(encoding='utf-8').splitlines() if x.strip()]
    if not records or any(not isinstance(r.get('prompt'), str) or not isinstance(r.get('output_tokens'), int) or r['output_tokens'] <= 0 for r in records):
        parser.error('Dataset needs nonempty prompt and positive output_tokens in every row')
    out = args.output_dir.resolve()
    cmd = command(args, out / 'dataset.jsonl', len(records), out)
    if args.dry_run:
        print(json.dumps(cmd, ensure_ascii=False, indent=2))
        return
    if importlib.metadata.version('vllm') != '0.31.0':
        parser.error('This runner was verified against vLLM 0.31.0; check CLI semantics before upgrading')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(dataset, out / 'dataset.jsonl')
    manifest = {'started_utc': datetime.now(timezone.utc).isoformat(), 'command': cmd,
                'dataset_sha256': hashlib.sha256((out / 'dataset.jsonl').read_bytes()).hexdigest(),
                'apc_expected': args.apc, 'cache_state': args.cache_state,
                'warmups': args.warmups, 'status': 'preparing',
                'versions': {p: importlib.metadata.version(p) for p in ('vllm', 'torch', 'transformers')}}
    manifest_path = out / 'manifest.json'

    def save():
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def metrics(filename):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(args.base_url + '/metrics', timeout=10) as r:
            (out / filename).write_bytes(r.read())

    def generate(prompt, length):
        result = request_json(args.base_url, '/v1/chat/completions',
                              {'model': args.model, 'messages': [{'role': 'user', 'content': prompt}],
                               'max_tokens': length, 'temperature': 0, 'ignore_eos': True})
        if not result.get('choices'):
            raise RuntimeError(f'Warmup did not produce choices: {result}')
        return result.get('usage')

    save()
    try:
        request_json(args.base_url, '/health')
        config = request_json(args.base_url, '/server_info?config_format=json')['vllm_config']
        cache = config['cache_config']
        if cache['enable_prefix_caching'] != (args.apc == 'on'):
            raise RuntimeError('Requested APC state differs from server configuration')
        # Record only relevant configuration, never the server environment.
        manifest['server_config'] = {section: {k: config[section].get(k) for k in keys} for section, keys in {
            'model_config': ('model', 'revision', 'tokenizer_revision', 'dtype', 'max_model_len'),
            'cache_config': ('enable_prefix_caching', 'block_size', 'gpu_memory_utilization', 'cache_dtype'),
            'scheduler_config': ('max_num_seqs', 'max_num_batched_tokens', 'enable_chunked_prefill'),
        }.items()}
        # Warm the service on unrelated text. Reset afterwards, so this is not APC prefill.
        manifest['service_warmup_usage'] = []
        if args.warmups:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        for i in range(args.warmups):
            prompt = warmup_prompt(tokenizer, i, config['model_config']['max_model_len'])
            manifest['service_warmup_usage'].append(generate(prompt, 64))
        if args.apc == 'on':
            reset_cache(args.base_url)
            manifest['cache_reset_success'] = True
        else:
            manifest['cache_reset_success'] = None  # APC disabled; nothing to clear.
        if args.cache_state == 'hot':
            # Same extra request in both modes; cache benefit exists only with APC enabled.
            manifest['prefix_warmup_usage'] = generate(records[0]['prompt'], records[0]['output_tokens'])
        manifest['status'] = 'running'
        save()
        metrics('metrics_before.txt')
        with (out / 'benchmark.log').open('w', encoding='utf-8') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=args.timeout)
        metrics('metrics_after.txt')
        result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
        if result['completed'] != len(records) or result['failed']:
            raise RuntimeError('Benchmark contains failed/missing requests; inspect result.json and benchmark.log')
        if result.get('output_lens') != [r['output_tokens'] for r in records]:
            raise RuntimeError('Actual output lengths differ from the controlled output lengths')
        manifest['status'] = 'completed'
        print(out / 'result.json')
    except Exception as e:
        manifest['status'] = 'failed'
        manifest['error'] = str(e)
        raise
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == '__main__':
    main()
