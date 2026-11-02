"""Evaluate GitHub job results; branch authority comes from the event, not inputs."""

import argparse
import json
import os
from pathlib import Path
import sys

CORE_CHECKS = ('workflow', 'contracts', 'data', 'package')
APPLICATION_CHECKS = ('backend', 'postgres', 'ai', 'parity', 'e2e', 'application-artifact')


def target_branch(event_name: str, ref: str, event: dict) -> str:
    if event_name == 'pull_request':
        branch = event.get('pull_request', {}).get('base', {}).get('ref')
    elif event_name in ('push', 'workflow_dispatch') and ref.startswith('refs/heads/'):
        branch = ref.removeprefix('refs/heads/')
    else:
        raise ValueError(f'Unsupported CI context: {event_name!r}, {ref!r}')
    if branch not in ('develop', 'main'):
        raise ValueError(f'Unsupported target branch: {branch!r}')
    return branch


def failed_checks(needs: dict, required: tuple[str, ...]) -> list[str]:
    failures = []
    for name in required:
        entry = needs.get(name)
        result = entry.get('result') if isinstance(entry, dict) else None
        if result != 'success':
            failures.append(f'{name}: {result or "missing"}')
    return failures


def evaluate(mode: str, branch: str, needs: dict) -> list[str]:
    if branch not in ('develop', 'main'):
        raise ValueError(f'Unsupported target branch: {branch!r}')
    if mode == 'release':
        if branch != 'main':
            return ['Release evaluation is allowed only for a main candidate']
        return failed_checks(needs, CORE_CHECKS + APPLICATION_CHECKS)
    if mode != 'ci':
        raise ValueError(f'Unknown gate: {mode}')
    required = CORE_CHECKS + (('release-readiness',) if branch == 'main' else ())
    failures = failed_checks(needs, required)
    if branch == 'develop':
        release = needs.get('release-readiness')
        if not isinstance(release, dict) or release.get('result') != 'skipped':
            failures.append('release-readiness: expected explicit not-applicable skip on develop')
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('ci', 'release'))
    args = parser.parse_args()
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
    branch = target_branch(os.environ['GITHUB_EVENT_NAME'], os.environ['GITHUB_REF'], event)
    needs = json.loads(os.environ['CI_NEEDS_JSON'])
    if not isinstance(needs, dict):
        raise ValueError('needs must be a JSON object')
    failures = evaluate(args.mode, branch, needs)
    lines = [f'{args.mode} gate on {branch}: {"FAIL" if failures else "PASS"}']
    lines.extend(f'- {failure}' for failure in failures)
    if args.mode == 'ci' and branch == 'develop' and not failures:
        lines.append('Data/contracts increment verified; this is not application release readiness.')
    if args.mode == 'release' and failures:
        lines.append('Wire executable application jobs into release-readiness.needs before releasing.')
    output = '\n'.join(lines) + '\n'
    print(output, end='')
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a', encoding='utf-8') as stream:
            stream.write(output)
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
