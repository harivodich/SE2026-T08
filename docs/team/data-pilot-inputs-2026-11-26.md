# Data pilot inputs — 26/11/2026

Increment source: `95648361ffc24c72efd16898994d85ee4ca7c786` plus scoped Data
working diff. Build/receiver commands: [PILOT-PACKET.md](../../src/vietdoc/data/PILOT-PACKET.md).
Actual hashes, counts, verification and remaining gaps are recorded in
[controller acceptance](role-unblock-acceptance-2026-11-26.md); initial producer
implementation/handoff receipts are retained in the external evidence bundle.

New dataset `v0.2-pilot-20261126`, seed `20261126`: receipt/invoice families
00/01 train and 06/07 dev, 5 bases per family, 4 variants per base. This is a
40-base/160-variant working input target, separate from historical 16-base smoke.
Historical final families 08/09 are never generated or transferred. Rows
0/1/3/12/30 are stress slices; renderer raises on overflow rather than dropping
rows/text. All variants retain source/base/family/split identity.

AI1 can verify and run native OCR independently on these real assets; AI2 can
exercise the records reader, typed four-state supervision and token preflight.
Use `vietdoc_ocr_context_v2`: OCR 6784 / input 7424 / output 1280 / sequence 8704.
Thirty rows may exceed capacity; account for overflow by exact sample ID.

Automated rerender, semantic join, pixel/hash and grouping checks are explicitly
AI-assisted evidence. Pending duplicate pairs remain unresolved and the planner
quarantines their complete components. OCR development inputs are distinct from
approved training membership. No new human verdict/ACK, independent review,
training clearance, quality acceptance or final-open authority is asserted.

The controller subsequently reviewed all 40 clean bases using images, business
values and independent synthetic seeds, producing a separate 410-pair reviewed
supplement and plan in `datasets/manifests/pilot-20261126-*`. Native OCR160/160
and token/consumer receipts now exist; use the current controller report and
Lead's PR decision. The original producer packet deliberately retains pending
review history and is never silently rewritten into a human approval.

Data-owned final QA uses the existing evaluator after candidate freeze and
authorized final protocol. On exposed train/dev inputs the deterministic command
is `python -m vietdoc.evaluation --root RECEIVER --manifest RECEIVER/dataset/manifest.json --candidate B0=B0.json --candidate M0=M0.json --candidate M1=M1.json --output NEW_REPORT`.
Require predictions covering the requested population, matching dataset version,
manifest/schema/model/source/profile hashes and explicit failure accounting.
Do not point this command at historical final assets or tune using final scores.
