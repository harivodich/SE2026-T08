# Integration exposure ledger — 23/11/2026

M08 is an independently executable R07/R10 preparation increment. It conservatively
records existing exposed integration data, not a claim that every person viewed
every image. No new final input/gold was opened or evaluated.

- [D1.2 full20](../../datasets/manifests/d12-exposure-20261123.json): 20 IDs.
- [D2.2 historical smoke](../../datasets/manifests/d22-exposure-20261123.json): 80 IDs,
  including its already exposed IDs named final; `final_frozen=false` at source.
- [Tracked D1.2 evaluator fixtures](../../datasets/manifests/d12-fixture-exposure-20261123.json):
  two IDs with their exact fixture hashes, retained even if IDs overlap full20.

Actual capture commands, from repo root in the Data environment, use:

```sh
PYTHONPATH=src python3 -B -m vietdoc.data.exposure record \
  --root <source-schema-root> --manifest <validated-asset-manifest> \
  --reference <exposure-evidence-reference> --output <new-ledger.json>
```

All three were run against existing local artifacts through the whole-source
records validator. Full20 uses the fresh verified root from M04, D22 uses
`datasets/processed/d22-smoke-c/manifest.json`, and fixtures use
`tests/fixtures/d12/manifest.json`. The outputs contain metadata/hashes only.
Unknown legacy source/assignment/content lineage remains null, never invented.
Known sample/base/family/source/assignment identities and PNG/gold/content/source-gold
hashes are retained. This is a dataset exposure inventory, not a comprehensive
authenticated access audit or structural-independence proof.

Metadata-only preflight (repeat `--ledger` for all applicable versions):

```sh
PYTHONPATH=src python3 -B -m vietdoc.data.exposure check \
  --ledger datasets/manifests/d12-exposure-20261123.json \
  --ledger datasets/manifests/d12-fixture-exposure-20261123.json \
  --ledger datasets/manifests/d22-exposure-20261123.json \
  --manifest <candidate-metadata.json> --output <new-preflight.json>
```

Preflight rejects overlap on any known identity/hash, including candidates with
new IDs but reused bytes/content or family/source/group. Empty populations,
duplicate candidate IDs, bad hashes and unknown ledger versions fail explicitly.
It does not read candidate PNG/gold bytes, certify the metadata, validate assets,
grant final-open permission, replace group/split approval or detect every possible
structural clone. Follow it with the owning integrity/lineage/split checks and Lead
decision. A clean preflight result is `no_known_exposure_overlap`, never approval.

Four focused tests PASS, including a real two-sample renderer fixture and overlap
controls for every identity/hash field. Actual normal/-O checks rejected the
historical D22 snapshot with no output; 20/20 full20, 80/80 D22 and 2/2 fixture members were also
checked individually and rejected. No final population was supplied. This suite
was added after the main Data suite was collected; its focused execution is tracked
separately rather than misreported as part of that earlier collection.

Keep these versions immutable and add ledgers when data is exposed. Recording a
ledger does not erase exposure or clear pending duplicate review. Final membership,
unexposed source/layout support and access/custodian decisions remain with Lead.
