"""Preserve accepted PR ancestry on a new local ref without changing its tree.

Input is `gh pr list --state all --json number,state,headRefOid,mergeCommit,...`.
Fetch merged PR heads and merge commits first. Never includes open/closed-unmerged
PRs, updates an existing branch, pushes, or changes a worktree/index.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

SHA = re.compile(r'[0-9a-f]{40}')


def git(repo, *args, input=None):
    command = ['git', '-c', f'safe.directory={repo}', '-C', str(repo), *args]
    result = subprocess.run(command, input=input, capture_output=True, text=True,
                            encoding='utf8', timeout=120)
    if result.returncode:
        raise ValueError(f'git {args[0]} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def ancestor(repo, commit, tip):
    result = subprocess.run(['git', '-c', f'safe.directory={repo}', '-C', str(repo),
                             'merge-base', '--is-ancestor', commit, tip], capture_output=True)
    if result.returncode not in (0, 1):
        raise ValueError('Missing commit object while checking ancestry')
    return result.returncode == 0


def inventory(repo, prs, base, main, historical_prs=()):
    repo = Path(repo).resolve()
    base = git(repo, 'rev-parse', '--verify', base + '^{commit}')
    main = git(repo, 'rev-parse', '--verify', main + '^{commit}')
    if git(repo, 'rev-parse', '--is-shallow-repository') != 'false':
        raise ValueError('Full history is required; shallow repository rejected')
    merged, seen = [], set()
    if not isinstance(prs, list):
        raise ValueError('Expected GitHub PR list')
    for pr in prs:
        if pr.get('state') != 'MERGED':
            continue
        number, head, merge = pr.get('number'), pr.get('headRefOid'), pr.get('mergeCommit')
        if (type(number) is not int or number <= 0 or number in seen or
                not isinstance(head, str) or not SHA.fullmatch(head) or
                not isinstance(merge, dict) or not SHA.fullmatch(str(merge.get('oid', '')))):
            raise ValueError('Invalid or duplicate merged PR metadata')
        seen.add(number)
        for commit in (head, merge['oid']):
            git(repo, 'cat-file', '-e', commit + '^{commit}')
        merged.append(dict(number=number, head=head, merge=merge['oid'],
                           target=pr.get('baseRefName')))
    if not merged:
        raise ValueError('No merged PRs supplied')
    if not set(historical_prs) <= seen:
        raise ValueError('Historical-only selection contains a missing or unmerged PR')
    primary = [pr for pr in merged if pr['target'] in ('main', 'develop')
               and (ancestor(repo, pr['merge'], base) or ancestor(repo, pr['merge'], main))]
    # A PR into another feature branch must actually be an ancestor of a received
    # primary PR head. Mere MERGED status on an unrelated branch is insufficient.
    unresolved = []
    for pr in merged:
        witnesses = [p['number'] for p in primary
                     if ancestor(repo, pr['merge'], p['head'])]
        historical = pr['number'] in historical_prs
        if historical and pr['target'] not in ('main', 'develop'):
            raise ValueError('Historical-only override is limited to previously merged primary-branch PRs')
        accepted = pr in primary or bool(witnesses) or historical
        pr.update(integration_verified=accepted, integrating_primary_prs=witnesses,
                  historical_only=historical, already_reachable=ancestor(repo, pr['head'], base))
        if not accepted:
            unresolved.append(pr['number'])
    return dict(base=base, main=main, tree=git(repo, 'rev-parse', base + '^{tree}'),
                base_commit_count=int(git(repo, 'rev-list', '--count', base)),
                merged_prs=sorted(merged, key=lambda p: p['number']), unresolved=unresolved,
                scope='Ancestry only; accepted source tree unchanged. Not code re-integration or release acceptance.')


def prepare(repo, report, branch):
    repo = Path(repo).resolve()
    if report['unresolved']:
        raise ValueError(f"Unproven integration: {report['unresolved']}")
    if not branch.startswith('release/'):
        raise ValueError('Use a new release/ branch, never main/develop')
    git(repo, 'check-ref-format', '--branch', branch)
    existing = subprocess.run(['git', '-c', f'safe.directory={repo}', '-C', str(repo),
                               'show-ref', '--verify', '--quiet', 'refs/heads/' + branch])
    if existing.returncode != 1:
        raise ValueError('Branch already exists or ref cannot be inspected; never overwrite it')
    before = git(repo, 'rev-parse', 'HEAD')
    status_before = git(repo, 'status', '--porcelain=v1')
    tip, added = report['base'], []
    # One honest history-only merge is enough. Git can accept several parents;
    # retain only maximal missing heads to avoid redundant ancestry edges.
    missing = sorted({tip for p in report['merged_prs'] for tip in (p['head'], p['merge'])
                      if not ancestor(repo, tip, report['base'])})
    maximal = [head for head in missing if not any(head != other and ancestor(repo, head, other)
                                                  for other in missing)]
    if maximal:
        parents = [arg for head in [tip, *maximal] for arg in ('-p', head)]
        message = ('Preserve accepted PR history without changing release source\n\n'
                   'History-only merge: original commits keep their SHA, author and date.\n'
                   f"Source tree stays exactly {report['base']}.\n"
                   'No additional feature code is accepted by this ancestry operation.\n'
                   'Historical reverted PRs are retained as history, not restored code.\n')
        tip = git(repo, 'commit-tree', report['tree'], *parents, input=message)
        added = maximal
    if git(repo, 'rev-parse', tip + '^{tree}') != report['tree']:
        raise ValueError('Source tree changed')
    for pr in report['merged_prs']:
        if not ancestor(repo, pr['head'], tip):
            raise ValueError(f"Original head not reachable: PR{pr['number']}")
        if not ancestor(repo, pr['merge'], tip):
            raise ValueError(f"Original merge not reachable: PR{pr['number']}")
    if before != git(repo, 'rev-parse', 'HEAD') or status_before != git(repo, 'status', '--porcelain=v1'):
        raise ValueError('Worktree changed concurrently; do not publish a candidate ref')
    # Empty old OID requires ref not to exist, atomically; no reset/force update.
    git(repo, 'update-ref', 'refs/heads/' + branch, tip, '0' * 40)
    return dict(report, branch=branch, tip=tip, added_history_parents=added,
                commit_count=int(git(repo, 'rev-list', '--count', tip)),
                source_tree_unchanged=True, all_original_heads_reachable=True,
                publication='local ref only; merge-commit PR required, never squash/rebase')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--prs', type=Path, required=True)
    parser.add_argument('--base', default='origin/develop')
    parser.add_argument('--main', default='origin/main')
    parser.add_argument('--prepare-branch')
    parser.add_argument('--historical-pr', type=int, action='append', default=[],
                        help='Explicitly retain a reverted primary-branch PR as historical-only, never restore its code')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; preserve previous evidence')
    report = inventory(args.repo, json.loads(args.prs.read_text(encoding='utf-8-sig')),
                       args.base, args.main, args.historical_pr)
    if args.prepare_branch:
        report = prepare(args.repo, report, args.prepare_branch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: value for key, value in report.items() if key != 'merged_prs'}))


if __name__ == '__main__':
    main()
