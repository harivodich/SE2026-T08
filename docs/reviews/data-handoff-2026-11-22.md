# #22/#36 — full20 and label records, 22/11/2026

Mini tasks B1/B2/B3/C1/C2; Data self-run only. AI1 receiver/native20 and AI2
actual training reader/batch ACK remain pending. No upload or consumer message was
sent in this run. [Safe receipt/pins](data-full20-receipt-2026-11-22.json) and
[two-type four-state vectors](data-label-vectors-2026-11-22.json) accompany this report.

## Full20 verification

Existing bundle `artifacts/evaluation/data-delivery-20261107-48yxYF/full-final`
was verified with the candidate's actual verifier, without rerender or repack:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.generator.handoff verify \
  --bundle artifacts/evaluation/data-delivery-20261107-48yxYF/full-final \
  --output artifacts/evaluation/data-increments-20261122/full20-verified
```

Exit 0: 20 IDs, 10 receipt + 10 invoice, 204 rows, 102 members. Manifest SHA-256
`093b8f772d19e5357ee6209f3358f44d7a072f457aaef64507f38081c0e70e9a`;
archive SHA-256 `a660f7d52abaf4d28c3bcd7db7814560cf40675ab6e42ff1e7db88915bbbcf0d`.
Archive/inventory/checksum bytes match the historical receipt; no hash update.

The [existing transfer attachment](https://github.com/user-attachments/files/34526599/full20-transfer.zip)
was posted in [#22](https://github.com/harivodich/SE2026-T08/issues/22#issuecomment-6711644580).
This run did not download it or verify receiver access. Receiver must unpack the
outer transfer ZIP, locate the folder containing `d12-handoff.zip`, `inventory.json`
and `SHA256SUMS`, and run `verify --bundle THAT_FOLDER --output NEW_ROOT`.
Only exit 0 with the expected manifest hash/counts establishes Data verification.
Asset paths then resolve relative to NEW_ROOT, not to `datasets/manifests`.

Handoff suite: 11 tests PASS (13.627 s). Two new negatives bind updated archive/
manifest checksums before testing missing-member and aliased-ID rejection, and
assert no output publication. Existing traversal, duplicate-member, modified-file,
symlink, no-overwrite and normal/-O regressions remain. Schema/gold/label semantic
guards are also exercised by adapter/evaluator/review regressions.

## Record export and consumer contract

Actual full20 export, after successful verification:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -B -m vietdoc.data.adapters.records \
  --root artifacts/evaluation/data-increments-20261122/full20-verified \
  --manifest artifacts/evaluation/data-increments-20261122/full20-verified/datasets/manifests/d12-integration-v2.json \
  --full-set --output artifacts/evaluation/data-increments-20261122/full20-records.json
```

Exit 0; `vietdoc.training-records.v1`, label adapter `vietdoc.field-labels.v1`;
20 records, 1138 present + 12 absent labels. JSON SHA-256
`aca61aaa4da1cbbedcd5e6c4ac3e85d748606cac592f456e78d134c42f725e8f`.
Each record preserves sample metadata, relative asset paths/hashes, validated gold
and exact field pointers/statuses. Records have not been used as inference input.

The real business schema requires **all** listed keys, including nullable ones:

| Type | Required scalar keys, plus `items` |
|---|---|
| receipt | merchant_name, merchant_address, transaction_date, transaction_time, total_amount |
| invoice | invoice_number, issue_date, seller_name, buyer_name, subtotal, tax_amount, discount_amount, total_amount |

Each item requires description/quantity/unit/unit_price/line_total. No extra keys;
items may be empty, max 30. Nullability is not permission to omit a required key.
Decimal values remain strings; dates must also pass semantic calendar validation.
Business schema is unchanged; [adapter contract](../label-adapter.md) is offline API
documentation, not a replacement schema.

| Data status | Export value | AI2 target/mask/loss acceptance |
|---|---|---|
| present | Original business string | Target/normalization must match the approved model reader |
| absent | null | Keep labeled absence separate; supervision policy pending AI2 |
| obscured | null | No readable value truth; must not silently become absent negative |
| unlabeled | null | Unknown annotation; mask or exclude per reviewed consumer policy |

Existing D1.1 receipt/invoice content-only fixtures demonstrate all four states;
the linked vectors were produced with the actual accessor. They are not renderer
certification or a training batch. D1 rendered full20 has only present/absent;
D2 content-loss exporter regression uses real fresh bounded rendered variants and
checks obscured values stay null. No invented renderer unlabeled coverage.

Exporter suite: 5 tests PASS (15.777 s), covering real tiny renderer replay, D2
relative-root/content-loss, no-overwrite/no partial publication, manifest drift
and normal/-O CLI. An initial round-trip test exposed tuple/list output mismatch;
the exporter now explicitly serializes field arrays. Tests were not weakened.

## Pending receipts

- AI1: receiver SHA/count verification, then native20 requested/attempted/ok/failed/
  not_run ledger with input/runtime/model pins at #41; Data verify20 is separate.
- AI2: reader sample ID/pointer/value/status replay, decoded actual batch and
  evidence for obscured/unlabeled masking or full-JSON sample exclusion at #52.
- Backend: full20 consumer receipt; Lead/peer: API semantics and current candidate
  acceptance. Data self-run and historical CI are not substitutes.

Large assets/records/logs remain ignored local artifacts. No dataset version,
final membership, Proposed policy, shared schema, CI or model/training source changed.
