# Non Moodle Acceptance Report

Date: 06/09/2026

Scope excludes Moodle installation, import, grading and verify-read.

## Outcome

The production-like technical drills passed for readiness, bounded load, OCR worker recovery, Mongo and artifact backup/restore, and Chroma rebuild/search. PDF and DOCX output now renders rich content across four variants and seven question types. The overall non-Moodle acceptance gate remains open only for evidence that cannot be created from the repository alone: a licensed CTDL corpus with frozen expert labels, named teacher/reviewer UAT, and authenticated workload testing with the target identity environment.

## Results

| Area | Result | Evidence |
|---|---:|---|
| Production-like readiness | PASS | Mongo replica-set transactions, writable storage and LOCAL_ONLY inference all ready |
| Load smoke | PASS | 100 requests at concurrency 10; 0 errors; p95 34.17 ms |
| Sustained bounded load | PASS | 2,000 requests at concurrency 50; 0 errors; p95 217.33 ms; 470.97 requests/s |
| OCR worker crash/restart | PASS | Worker killed during PROCESSING; retry attempt 2; fencing token 2; 300 unique contiguous pages |
| Mongo backup/restore | PASS | Both application databases matched collection counts and canonical document hashes |
| Artifact backup/restore | PASS | All 11 source files matched restored byte counts and SHA-256 hashes |
| Isolated drill RTO/RPO | PASS WITH SCOPE LIMIT | RTO 4.422 s; RPO 0 s while writes were quiesced; fixture volume only |
| Chroma rebuild/search | PASS | Re-indexed from restored Mongo chunks into a new collection; hybrid recall@5 remained 1.0 on 5 fixture queries |
| Retrieval quality | PARTIAL | Vietnamese bi-encoder improved dense recall@5 from 0.2 to 0.6; hybrid and lexical remain 1.0; corpus is the project-proposal PDF, not licensed CTDL |
| Export structure | PASS | 16 files; answer mapping and student-answer separation checks passed |
| PDF and DOCX visual layout | PASS | 24 rendered pages inspected; no clipping, overlap or broken Vietnamese glyphs |
| Rich-content export | PASS | Inline/fenced code, Markdown table, MathML/OMML formula and embedded PNG rendered; unsafe HTML escaped |
| Automated non-Moodle regression | PASS | Backend 240 passed plus 14 subtests (9 external-profile skips); Mongo profile 9 passed; frontend 47 passed; browser roles 3 passed; lint/build passed |
| External teacher/reviewer UAT | NOT RUN | Requires named external testers, approved dataset/license, screenshots and sign-off |

## Important limitations

- The load target was `/health/ready`; this proves bounded service/readiness behavior, not authenticated end-to-end capacity.
- Dense retrieval improved to 0.6 recall@5 with `bkai-foundation-models/vietnamese-bi-encoder`; this five-query repository fixture is too small and is not the licensed CTDL acceptance corpus, so it cannot close the quality gate.
- The embedding release is pinned in the sample environment to revision `84f9d9ada0d1a3c37557398b9ae9fcedcdf40be0` and artifact SHA-256 `e681accadaec87e79901db0c3f68e33d996cba334633b6dd0b2483dba4f398e0`.
- Recovered document jobs now clear stale job/document errors on successful completion. The follow-up recovery drill completed 300 unique contiguous pages with attempt/fencing token 2 and `error=null`.
- Human UAT and CTDL quality claims cannot be manufactured from automated fixtures. They remain external acceptance work.

## Evidence files

- `logs/load-smoke-100x10.json`
- `logs/load-sustained-2000x50.json`
- `logs/worker-crash-recovery.json`
- `logs/backup-restore.json`
- `logs/retrieval-local-benchmark.json`
- `logs/retrieval-multilingual-benchmark.json`
- `logs/retrieval-vietnamese-benchmark.json`
- `logs/retrieval-after-rebuild.json`
- `logs/visual-export-qa.json`
- `logs/worker-stale-recovery-followup.json`
- `exports/export-manifest.json`

The PDF/DOCX outputs and rendered QA PNGs are reproducible with the committed
acceptance script. They are intentionally excluded from source control; the
manifest and QA log retain the machine-readable verification evidence.
