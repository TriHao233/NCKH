# Operations and acceptance runbook

## Release gates

Run backend unit tests, the mandatory Mongo replica-set profile, Moodle contract profile, frontend
tests/lint/build and three-role Chromium E2E from `.github/workflows/p0-tests.yml`. A release fails if
any required profile is skipped. External Moodle round-trip and licensed-corpus studies remain signed
artifacts, not CI simulations.

## Startup and readiness

- `/health/live` proves the API process responds.
- `/health/ready` returns 200 only when Mongo responds, required transactions are supported, artifact
  directories exist and production inference policy is local-only.
- Admin job metrics expose queue age, expired leases, dead letters, Moodle `UNKNOWN` counts and alerts.
- Alert immediately on expired leases or Moodle UNKNOWN; investigate dead letters and queue age over
  15 minutes. Do not restart workers until lease ownership and idempotency keys are understood.

Production uses `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`. Put TLS and
authentication at the reverse proxy; inject Firebase/Moodle secrets outside Git. Mongo is not exposed
by the production override.

## Recovery and backup drill

1. Stop one worker during PROCESSING, wait for lease expiry, restart it and run recovery. Verify the
   stale job is retried once and finalized outputs are not duplicated.
2. Run `python scripts/mongo_backup_restore_drill.py --uri ... --source-db NCKH --drill-db NCKH_restore_drill --output ...`.
   The script refuses the source DB as restore target and writes per-file SHA-256 plus measured timestamps.
3. Compare collection counts and sample content hashes in the isolated drill DB. Record RPO/RTO and
   operator identity. Delete the drill DB later through the approved database process, not this script.
4. Run `python scripts/load_smoke.py --base-url ... --requests 100 --concurrency 10`; preserve the JSON
   denominator, error count and latency. This smoke is not a capacity benchmark.

## Holdout and human review

Freeze the licensed dataset split and model/prompt digests before evaluation. Each JSONL row must retain
case ID, split, decision (`PASS`, `FAIL`, or explicit exclusion), error category and pseudonymous reviewer
ID. Generate the report with `scripts/holdout_report.py`; it records denominator, exclusions, reviewer
count, model digest and report hash. Report every predefined slice and failure category; do not remove
failed or no-data cases after viewing results.

## UAT scripts

- Teacher: upload text/scan/mixed PDF, inspect/correct a revision, generate and submit questions, build
  a Blueprint V2 exam, finalize, create four variants and inspect student/answer files.
- Reviewer: claim a submitted question, inspect exact PDF evidence spans and AI no-data/hard failures,
  comment, revise/approve, and verify lock expiry behavior.
- Admin: manage memberships and model releases, inspect queue alerts, configure Moodle target, process a
  publication and reconcile UNKNOWN without blind retry.

For every script record tester, timestamp, environment/build digest, input IDs, expected/actual result,
screenshots or artifact checksums, and PASS/FAIL. Final sign-off requires at least one person outside the
development team per role, the approved demo dataset/license, visual PDF QA and a real Moodle verify-read.
