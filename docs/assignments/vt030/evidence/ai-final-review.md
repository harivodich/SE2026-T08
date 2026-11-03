# BT3 VT-030 final review (claude-final, claude-opus-5-5/xhigh, read-only)

**Source identity:** I reviewed the snapshot at e3b3850 plus the uncommitted docs/evidence. Context_id is 20014992…e095f. The inputs were brief-final.md (167eef76…) and final-source-00/01/02 (e146cac9…, 7518771b…, 564d889d…), all read in full. I made no extra Read calls and ran nothing. The summary did not include the OpenAPI diff, the red-native and load-repeat run metadata, the raw logs and outcome arrays, or a rendered PDF, so I did not review those. I wrote no files: the brief forbids writes, and no Write or ExitPlanMode tool was available.

## Verdict

The technical handoff is **acceptable with residuals**. I found no confirmed P1 defect in the production code, tests or measurements. Two P1 submission gates and several cheap P2 corrections remain. The student still owns the final read and the submission; this review does not accept the work on their behalf.

## P1: submission gates (current state, not code defects)

**P1-1. The branch and README requirement is not met yet.** README, evidence and report are uncommitted, but the report and README already link `tree/codex/bt3-vt030-async-idempotency` and cite 2d34f4c and e3b3850.
- **Fix (needs human authorization):** commit `docs/assignments/vt030/`, plus the scripts if they aren't already in e3b3850. Push the branch, then check that the link shows the README and that 2d34f4c and e3b3850 exist on the remote.
- If a docs commit becomes the new head, cite it. 09cd8a2 stays local only, which the report already says.

**P1-2. The PDF has not been rendered.** Check four things:
- There are at most 8 main pages. Pages 4–6 have dense tables and could overflow past the forced page breaks.
- The "trang 7" cross-reference in §5 still points to the right page.
- The filename is `BT3_23001870_VT-030.pdf`.
- The body text is consistently Times New Roman, black, regular.

## P2 findings

1. **Equivalence partitioning is only implicit.** This is the technique the assignment requires. §3 lists the classes but never maps them to test cases. **Fix:** add the IDs inline in the existing sentence:
   - key: valid (TC01/19), missing (TC14), malformed (TC05), overlong (TC20)
   - key/document: same doc and key (TC03), different key while active (TC04), same key on another doc (TC09)
   - caller: owner, foreign, anonymous (TC01/08/07)
   - job state: active, retrying, succeeded, failed, cancelled (TC04/11/10/15/12)
   - claim: stale (TC11), expired (TC13)
   - quota: at limit (TC21)
2. **The traceability column "S/P" overstates test-first (confirmed).** The red run had 15 contract methods, so TC19–21 exist only in P; check whether the L and B files are in S. The red and green metadata files don't record the commit SHA. **Fix:** mark those rows P-only. Add `git diff --stat 729be6f 2d34f4c` (tests only) and `git diff --stat 2d34f4c e3b3850`, and compare commit times with the run times (red 19:06:07Z, green 19:15:41Z).
3. **Some load-report fields are hard-coded, not measured (confirmed).** `barrier_ready=count` and `all_outcomes_in_percentile=true` are constants written to the JSON *before* the assertions run. The published values are right only because those runs then passed. Also, each request's timer starts when its thread wakes, while timeouts are timed from the shared release. The same problem affects `vt030_mutation.py`: its `killed` check looks for "Vt030MappingTest" in the log, which Surefire's "Running" line always prints. **Fix:** add one disclosure sentence (no rerun needed), and cite the JUnit XML failure counts for the 7/7 mutation result.
4. **A 10× p95 gap is unexplained (cause unproven).** Independent users show 2252/2245 ms, same-key retries 205/223 ms, and the warm instrumented run 178.56 ms. This is probably a cold-JVM effect on whichever test runs first, not a cost of the scenario. **Fix:** add one sentence saying so and noting it makes the result conservative. Expect this question in the oral exam.
5. **There's no proof the random test order actually took effect.** **Fix:** compare the test-case order in the order-seed17 and order-seed83 XML files (against each other and against green) and cite that in §6.
6. **TC21's replay assertion is weak (confirmed).** It checks only `state=QUEUED`. The job count is checked *before* the replay, and the test never asserts the same job id. The report's wording ("replay cũ 202") matches what the test does, so keep the wording. Strengthen the test only if green, the full suite and coverage are all rerun.
7. **The README commands were not the ones executed.** Every real run used Git Bash `mvnw` with `-o`, empty settings and a custom Maven repository. The documented PowerShell `.\mvnw.cmd` commands and the `cmd /c mvnw.cmd` mutation command were never run. **Fix:** run one exactly as written, or label them "not executed; exact argv in *.json".
8. **The plan section doesn't list the files the AI planned to change**, which the rubric asks for. **Fix:** add one line comparing planned and actual files: the controller and OpenAPI changed; the queue and CacheControl changes were rejected.
9. **Some references are stale or dangling.**
   - `peer-review.md` must exist and contain this review and how each finding was resolved.
   - `manifest.json` must be regenerated after the final edits.
   - "red-native: 15 tests" next to the 21-test red run needs a note on what the first run covered.

**Unproven risks (no action required):**
- `Location` hard-codes `/api/v1/jobs/`, so it ignores any servlet context path or proxy prefix.
- I did not see the OpenAPI change.

**Optional:** cite RFC 9110 §15.3.3 (a 202 response "ought to … point to … a status monitor") to justify choosing `Location` as the slice. You could also note that TC04 shows a UI retry with a new key gets a 409 rather than a duplicate job, although the UI doesn't reconnect to the existing job.

## Confirmed checks

- **Test counts:**
  - Contract class: 15 + 2 + 1 + 1 = 19. Mapping: 6. Together 25, plus 2 load tests = 27 new.
  - Existing baseline tests: 2 + 2 + 1 + 18 = 23. Total 50.
  - The red run was 21 tests with 1 failure. The mutation filter covers 7 tests.
  - Repeated runs are not counted as new coverage.
- **Arithmetic:**
  - Coverage: 1162/1441 = 80.64% lines, 450/710 = 63.38% branches; JobService 88.27% / 64.52%. Marking branch coverage as N/A where there's no branch counter is correct.
  - RAM 15.21 GiB, and the p95 rank is ceil(0.95 × 200) = 190.
  - Every load figure matches its JSON. Peak 200 appears in both main runs, and the instrumented 195 is disclosed.
- **Excluded report:** the stale load-baseline XML has the same hash (be38fa…) as the raw red-run XML, which fits the "stale report copied by the runner" explanation.
- **Mutation:**
  - Order: the working-copy run (19:16:42Z) sits between green and the full suite (19:19:58Z).
  - Restore and source: the restored hash equals the original, the branch mutant is based on e3b3850, and the submitted mapper is unchanged.
  - Oracle: the expected IDs come from the uploaded document and fixed UUIDs, not from the mapper.
- **Compatibility:** status and body are unchanged. The security `no-store` header is kept (TC01), and the relative `Location` was confirmed through real Tomcat (E2E01).
- **First page:** name, student ID, VT-030, team, AI-02, repository plus the rename note, baseline commit, branch link, and the commitment sentence word for word.
- **Reflection:** 306 space-separated words (70/74/69/93 by paragraph), excluding the sources subsection. That is inside 250–350 and covers what raised confidence, what is still unproven, and the next test.
- **Lecture citations:** the slide numbers fall inside the 27- and 28-slide decks. Whether each slide covers the cited topic can't be checked here, so the student must verify them against the decks.
- **AI usage log:** four plan points rejected with repository evidence, and at least two plausible-but-untrustworthy AI outputs identified.

## Left for the student

- Authorize the commit and push, then check the link.
- Render and read the PDF.
- Check the slide citations against the decks.
- Be ready in the oral exam to explain the p95 index, the 10× gap, the mutation kill check, and the H2-vs-PostgreSQL limits.