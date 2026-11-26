"""Run the shared corpus through Python and compare actual Java results."""
import argparse
import hashlib
import json
from pathlib import Path

from vietdoc.contracts.compute import ComputeContracts, ContractError

ROOT = Path(__file__).resolve().parents[2]


def compare(corpus_path, java_path):
    raw = corpus_path.read_bytes()
    corpus = json.loads(raw)
    java = json.loads(java_path.read_text(encoding='utf8'))
    if corpus.get('version') != 1 or len(corpus['cases']) < 16:
        raise ValueError('Missing required parity corpus')
    digest = hashlib.sha256(raw).hexdigest()
    if java.get('corpus_sha256') != digest:
        raise ValueError('Java ran a different parity corpus')
    contracts = ComputeContracts(ROOT / 'specs/contracts')
    outcomes = {}
    for case in corpus['cases']:
        if case['id'] in outcomes or type(case['expected']) is not bool:
            raise ValueError('Invalid parity case')
        accepted = True
        try:
            contracts.validate('urn:vietdoc:compute-' + case['kind'] + ':v1', case['value'])
        except ContractError:
            accepted = False
        if accepted != case['expected']:
            raise ValueError('Python acceptance differs from oracle: ' + case['id'])
        outcomes[case['id']] = accepted
    if java.get('outcomes') != outcomes:
        raise ValueError('Java/Python contract parity mismatch')
    return dict(status='PASS', corpus_sha256=digest, cases=len(outcomes),
                scope='Shared positive/negative corpus; not proof of every schema/semantic input')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT / 'tests/contract/parity-cases.json')
    parser.add_argument('--java-results', type=Path, default=ROOT / 'backend/target/parity-java.json')
    args = parser.parse_args()
    print(json.dumps(compare(args.corpus, args.java_results)))


if __name__ == '__main__':
    main()
