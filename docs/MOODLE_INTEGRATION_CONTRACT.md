# Moodle integration contract

## Contract boundaries

1. Identity provisioning maps `(site_key, external_user_id)` to one internal user. Email is descriptive, not a merge key.
2. Course-role sync creates or revokes scoped `subject_memberships`; it never deletes authorship/review history.
3. File export produces GIFT/XML from the current approved question version and does not claim remote publication.
4. Question Bank publication must receive a remote question ID and verification response before status `PUBLISHED` with `external_sync=true`.
5. Quiz creation/delivery is a separate adapter and is not implied by Question Bank publication.

## Required Moodle administrator facts

| Item | Required value |
|---|---|
| Moodle version/build | Pending institutional confirmation |
| Integration method | Plugin or approved web-service functions |
| Test site/course/category | Pending |
| Service account | Least-privilege account, pending |
| Supported qtypes | Must be probed against the target version |
| SSO requirement | Pending; identity sync is the default first milestone |

## Publication request

The remote adapter receives target, course/category, question type, approved version ID,
content hash, serialized payload and idempotency key. Secrets are resolved from environment
variables at execution time and are never returned by APIs or written to publication records.

## Result semantics

- `QUEUED`/`PUBLISHING`: no remote success claim.
- `PUBLISHED`: remote ID is present and a verification read succeeded.
- `UNKNOWN`: request may have succeeded but confirmation was lost; reconcile before retry.
- `FAILED`: confirmed failure safe to retry using the same idempotency key.
- `MOCK`: local demonstration record only, always `external_sync=false`.

## Spike acceptance

The stage-A spike completes only when an administrator supplies the pending facts and the
repository contains an anonymized round-trip fixture exported from the actual Moodle target.

## Implemented technical contract (2026-09-06)

Backend serializer supports the seven typed question forms and declares a per-qtype capability
matrix. REST publication uses an idempotent Question Bank adapter, durable outbox states and a
verification read before remote `PUBLISHED`. Network ambiguity becomes `UNKNOWN` and requires
reconciliation. The versioned Moodle-side plugin is in `moodle/local/nckh`. Identity sync is keyed
by `(site_key, external_user_id)`, consumes verified link tokens, requires a contiguous numbered
checkpoint chain and revokes missing Moodle memberships only after an error-free final page.
See [MOODLE_CONNECTOR_RUNBOOK.md](D:/NCKH/docs/MOODLE_CONNECTOR_RUNBOOK.md).

This does not close the institutional gate: Moodle version/build, installed adapter, least-privilege
service account, real course/category and anonymized round-trip fixtures remain pending.
