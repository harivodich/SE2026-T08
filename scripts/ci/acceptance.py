"""Fail closed until the Lead's source-bound, frozen V1 quality packet exists.

This verifies the received packet; it never generates scores or grants approval.
Data's original report structure is retained through explicit JSON pointers.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
METRICS = {'raw_schema_validity', 'present_scalar_em', 'total_em', 'matched_cell_accuracy', 'exact_row_accuracy'}


def read(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Acceptance metadata exceeds size limit')
    return json.loads(path.read_text(encoding='utf8'), parse_float=Decimal)


def fingerprint(root):
    files = [p for folder in ('src/vietdoc', 'backend/src/main', 'specs/contracts')
             for p in (root / folder).rglob('*') if p.is_file() and
             '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.md')]
    runtime_entrypoint = root / 'scripts/serve_compute_candidate.py'
    if runtime_entrypoint.is_file():files.append(runtime_entrypoint)
    if not files:
        raise ValueError('Missing application source inventory')
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def pointer(document, path):
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('Metric JSON pointer required')
    for part in path[1:].split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        document = document[int(key)] if isinstance(document, list) else document[key]
    return document


def check(packet_path, root=ROOT):
    if not packet_path.is_file():
        raise ValueError('V1_NOT_READY: missing frozen quality/actual-candidate packet; baseline smoke is insufficient')
    packet = read(packet_path)
    if type(packet.get('version')) is not int or packet['version'] != 1 or packet.get('status') != 'accepted' or packet.get('final_status') != 'completed':
        raise ValueError('V1_NOT_READY: quality packet is not accepted/final-completed')
    if packet.get('source_files') != fingerprint(root):
        raise ValueError('V1_NOT_READY: accepted application source changed')
    base = packet_path.parent.resolve()
    documents = {}
    for name, record in packet['reports'].items():
        path = PurePosixPath(record['path'])
        if path.is_absolute() or any(p in ('..', '.') for p in path.parts) or '\\' in str(path) or ':' in str(path):
            raise ValueError('Unsafe acceptance report path')
        local = base.joinpath(*path.parts)
        if local.is_symlink() or not local.resolve().is_relative_to(base):
            raise ValueError('Acceptance report outside packet')
        if hashlib.sha256(local.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('Acceptance report bytes changed')
        documents[name] = read(local)
    policy = documents['policy']
    if policy.get('status') != 'frozen' or policy.get('final_open_permitted') is not True:
        raise ValueError('V1_NOT_READY: policy/final-open decision missing')
    required = {f'{kind}/{metric}' for kind in ('receipt', 'invoice') for metric in METRICS}
    checks = packet['checks']
    if len(checks) != len(required) or {c['id'] for c in checks} != required:
        raise ValueError('Incomplete per-type quality checks')
    for item in checks:
        minimum = policy['minimums'][item['id']]
        value = pointer(documents[item['report']], item['value_pointer'])
        support = pointer(documents[item['report']], item['support_pointer'])
        if type(support) is not int or support <= 0 or type(value) not in (int, Decimal) or type(minimum) not in (int, Decimal):
            raise ValueError('Unknown/zero-support/non-numeric quality cannot pass')
        if not Decimal(0) < minimum <= Decimal(1) or not Decimal(0) <= value <= Decimal(1) or value < minimum:
            raise ValueError('V1 quality target failed: ' + item['id'])
    candidate = documents['candidate_e2e']
    if (candidate.get('status') != 'PASS' or candidate.get('actual_native_provider') is not True or
            candidate.get('database') != 'PostgreSQL' or candidate.get('candidate_id') != packet['candidate_id'] or
            candidate.get('extractor') != 'qwen-local' or
            {c['type'] for c in candidate.get('cases', [])} != {'receipt', 'invoice'}):
        raise ValueError('V1_NOT_READY: actual accepted model E2E missing; B0/demo/fixture does not substitute')
    return dict(status='PASS', candidate_id=packet['candidate_id'], per_type_checks=len(checks),
                scope='Validated frozen quality packet; final raw evidence/replay remains Lead review responsibility')


def main():
    print(json.dumps(check(ROOT / 'docs/reviews/v1-acceptance/index.json')))


if __name__ == '__main__':
    main()
