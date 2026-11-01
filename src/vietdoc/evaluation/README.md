# D3.1 — offline scalar/OCR evaluator v2

Independent Data evaluator, stdlib only. Reads frozen artifacts; no inference, API,
production normalizer or final-test tuning.

D3.2 adds table/evidence/comparison and correctness export through `--candidate`;
see [D32 policy, protocol and commands](D32.md). Existing `--predictions` mode
retains the D3.1 behavior documented below.

## Policy and review status

`d31-canonical-nfc-v1-proposed` is **Proposed**, pending AI-1/AI-2 review.
Checkout has no M2.2 normalizer/policy implementation and no O1.3 output contract
implementation. Team task descriptions specify intent, not accepted conventions.
This evaluator changes no production normalization.
Evaluator `d3.1.v2` adds the strict-review boundary/compatibility fixes; D3.2 uses
`d3.2.v2`. Rescore candidates together rather than comparing old/new reports.

- NFC; preserve Vietnamese accents and case. Trim/collapse Unicode whitespace.
  Empty/whitespace-only scalar = missing. Pin Python Unicode database version.
- Money: canonical nonnegative decimal **strings** (max 32 chars), exact Decimal
  equality: `45000.00` = `45000`. No binary float or locale/currency parsing.
  `45.000` means canonical decimal 45, not raw Vietnamese grouping 45000;
  `45.000 đ` and `45,00` are invalid. AI-2 must normalize raw locale values before
  publishing canonical artifacts. Invalid nonempty predictions count FP+FN on
  present gold, FP/false fill on absent gold.
- Date: valid calendar `YYYY-MM-DD` only. Reject raw `DD/MM/YYYY`, invalid and
  ambiguous forms; no guessing. Time: valid `HH:MM[:SS]`, literal comparison
  (`10:05` differs from `10:05:00`). AI-2 review these canonical boundaries.
- OCR: same NFC/whitespace/case policy. CER uses Unicode codepoints including
  normalized spaces; WER splits on spaces, punctuation remains attached. Corpus
  micro aggregation, not mean sample rate. AI-1 must review reading-order join,
  whitespace, punctuation and empty-reference handling; exporter must materialize
  `ocr_text` in declared reading order. Evaluator never guesses block order.
- New renderer manifests declare `transcript_scope: "full_page"` and
  `transcript_order: "renderer-draw-call-v1"`. A versioned compatibility adapter
  recognizes historical D1.2 v1/v2 and D2.1/D2.2 v1 renderer transcripts with
  the same scope/order. Other formats must declare scope; QA/unknown scopes stay
  excluded. Reports retain scope/order per sample. Draw-call order joins wrapped
  cell fragments before subsequent cells; it is a description of current output,
  **not an accepted OCR reading-order protocol**. AI-1/Lead review is still required
  before interpreting actual CER/WER as model quality.

## Metrics and accounting

Each scalar slot is selected from the fixed business v1 fields for its type;
`items` excluded. Labels use JSON pointers as in D1.2. Missing label = unlabeled.
Inconsistent present/null or absent/nonempty gold raises an input error.
Labels must be a flat (possibly partial) pointer-to-object map, with a known status
and valid scalar or existing row/cell pointer. D1.1 envelopes, typo pointers and
non-object labels fail with sample ID before scoring/slice construction; no implicit
D1.1 adapter is provided. Obscured/unlabeled remain excluded, never absent.

| Gold status / prediction | Accounting |
| --- | --- |
| present, exact normalized value | TP |
| present, wrong nonempty / invalid value | FP + FN |
| present, missing key / null / empty | FN; separate `present_missing`, `present_null`, `present_empty` counts |
| absent, nonempty / invalid prediction | FP, `false_fill` |
| absent, empty | no TP/TN; absent support retained in counts |
| unlabeled / obscured, any prediction | excluded, separate counts; no TP/FP/FN |

EM = TP / present; precision = TP/(TP+FP); recall = TP/(TP+FN);
F1 = 2TP/(2TP+FP+FN). F1 is value-level micro F1. Absent slots never add
correct matches. Report `support` is present gold count; absent/excluded counts
remain explicit. Receipt/invoice, each field, critical total/date slices reported.
Critical fields are also visible per type in the per-field groups.

Every metric has numerator, denominator, support, exclusions and zero-denominator
behavior. Zero denominator yields JSON null, never automatic perfect score.
CER/WER numerator is Levenshtein edits, denominator reference chars/words;
support is eligible full-page transcript sample count. Empty-reference insertions
remain in numerator; corpus rates can exceed 1. An all-empty reference corpus
has null CER/WER even with insertions. Empty gold is eligible, not missing gold.

Sample ID matching is independent of record order. Missing, failed, duplicate and
invalid known-ID records score as empty predictions in scalar and eligible OCR
metrics. Duplicate IDs have no selected winner. Unknown IDs and all duplicates
are reported as integrity issues; unknown IDs have no gold and add no TP.
Prediction status/error and outcome remain in `samples`; field/transcript errors
include IDs, raw gold/prediction and categories. A missing OCR string with an
otherwise successful payload counts as empty OCR, with separate coverage count.
Consumers must inspect `issues`/`accounting`, not just the score.

## Input/output

Manifest: D1.2 shape with nonempty `version`, unique `sample_id`, `document_type`,
`schema_id: "urn:vietdoc:business:v1"`, and `assets` entries `gold.json`,
`labels.json`, optional `txt`. Each entry has `path` and `sha256`.
D1.2 paths are relative to `--root`; D2.1/D2.2 paths are relative to the manifest's
directory. Relocated D2 snapshots must retain their assets beside the manifest.
Only evaluator-consumed assets are loaded and hash verified, never images/models.
Paths must stay under their declared base. Gold itself uses business scalar keys; labels
are separate metadata. Versioned manifest pins gold/schema/transcript versions.

Prediction JSON envelope (local offline contract, not a change to shared schemas):

```json
{
  "artifact_version": "vietdoc.predictions.v1",
  "dataset_manifest_sha256": "<sha256 of exact manifest bytes>",
  "model_version": "<immutable release/revision or fixture-only.v1>",
  "normalizer_version": "<producer normalizer version>",
  "ocr_version": "<engine+model revision or not-applicable>",
  "predictions": [
    {"sample_id": "sample-id", "status": "ok", "payload": {"total_amount": "45000"}, "ocr_text": "..."},
    {"sample_id": "another-id", "status": "failed", "error": "timeout"}
  ]
}
```

Producer may include additional version/config/hardware metadata in the envelope;
all are pinned in the report alongside input SHA256, consumed asset hashes,
evaluator version and source SHA256. Payload may be omitted for OCR-only runs;
scalar values will then be reported missing. No auto conversion of live compute
responses: producers own export to this reviewable frozen artifact format.

`inputs.dataset_version` uses manifest `dataset_version`, falling back to `version`;
`manifest_format_version` separately records the format. A declared prediction
dataset version must match. Correctness exports and freeze preparation use the
same dataset/format distinction.

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests/unit -p test_evaluation.py -v
PYTHONPATH=src .venv/bin/python -m vietdoc.evaluation \
  --root . --manifest tests/fixtures/d12/manifest.json \
  --predictions tests/fixtures/d31-known-predictions.json \
  --output artifacts/evaluation/d31-known-score-v1-final
```

CLI creates a new directory containing `report.json` and `report.md`, refuses
overwrite. Markdown contains summary tables plus full accounting/provenance/error
data. Reports are ignored runtime artifacts. Tiny fictional fixtures are test
inputs, explicitly not B0/M0 model output. B0/M0 comparison awaits real artifacts.
