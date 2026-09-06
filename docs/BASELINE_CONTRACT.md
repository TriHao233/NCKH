# QBankCTU — Baseline contract A–H

Baseline version: **2026-09-06.1**. Branch: `feature/assessment-pipeline-roadmap`.

## Product boundary

- Required input: Vietnamese text, scanned and mixed PDFs; DOCX remains supported but is not the PDF acceptance path.
- Pilot domain: Data Structures. Subjects, chapters and CLOs are catalog data, never hard-coded by subject code.
- Roles are permission bundles. Authorization is `capability + active subject membership + resource state`.
- AI generation/evaluation is local in acceptance (`INFERENCE_POLICY=LOCAL_ONLY`). Firebase authentication may still require Internet.
- An AI output is a draft. A reviewer independent from the author/source owner approves a specific version.
- Official Moodle export accepts only the current approved version. CSV/XLSX are archival exchange formats and must retain status/version metadata.
- Current Moodle scope is GIFT/XML plus explicit local simulation. Remote Question Bank publication is stage G. Quiz creation is an optional, separate contract.

## Requirement and acceptance trace

| Requirement | Required outcome | Implementation task | Acceptance evidence |
|---|---|---|---|
| R-AUTH-01 | SUBJECT access requires active membership or subject ownership | B01/B02 | T06/T07 negative authorization tests |
| R-REV-01 | Author/source owner cannot self-review | B04 | T09 service/API test |
| R-REV-02 | Claim, assignment and decision use optimistic/CAS guards | B04 | T08 concurrent update test |
| R-EXP-01 | Single and bulk GIFT/XML share one backend eligibility rule | B03/B07 | T15 plus version-race test |
| R-EXP-02 | Batch export reports every rejected item and emits no partial official file | B03/B07 | mixed batch contract test |
| R-AI-01 | Main/code/evaluator/fallback use only allowlisted local endpoints | B05 | T24 policy tests |
| R-SEC-01 | Raw bearer tokens and target secrets are not persisted or returned | B06 | migration dry-run + repository tests |
| R-DOC-01 | Source extraction preserves raw page/code provenance | C01–C05 | T01–T05/T23/T25 |
| R-RAG-01 | Retrieval respects subject/chapter hard scope | D01–D04 | T05/G4 |
| R-EVAL-01 | AI scores cannot replace human approval or compensate hard failures | E01–E06 | G6/G7 |
| R-EXAM-01 | Finalized exams contain immutable approved snapshots and valid coverage | F01–F05 | T16–T19/G8 |
| R-LMS-01 | Remote Moodle publication is verified, scoped and idempotent | G01–G06 | T20–T22/T28/G9 |
| R-OPS-01 | Clean restore/recovery and research report are reproducible | H01–H06 | G10 and signed test report |

## Stage A decisions

| Decision | Baseline |
|---|---|
| Runtime | Python 3.10.14, Node 20.19.0, npm 10/11, MongoDB 7 replica set |
| Data stores | MongoDB is authoritative; Chroma is rebuildable; local artifacts preserve source files |
| Authentication | Keep Firebase adapter for now; Moodle identity/course sync is separate from SSO |
| Review policy | Independent reviewer; Admin has no implicit professional-review capability |
| CLO/chapter | CLO required before approval; chapter may be unclassified in draft |
| Code questions | Reading, tracing and debugging only; C/C++ is provisional until the pilot corpus is signed off |
| Moodle | Question Bank publication required in stage G; Quiz delivery is out unless explicitly accepted later |

## External decisions still required

These cannot be inferred from source code and block only the dependent stage, not B/C/D work:

- Exact institutional Moodle version, plugin/web-service installation authority and test course/category IDs.
- Service-account capabilities approved by the Moodle administrator.
- Licensed Data Structures corpus, official CLO revision and expert-labelled train/calibration/holdout split.
- Acceptance machine GPU/VRAM/RAM and expected concurrent users.
- Whether Moodle SSO and Quiz creation are included in final acceptance.

## Reproducible environment

1. Use versions from `.python-version` and `.nvmrc`; CI is the executable reference.
2. Copy `.env.example` files and provide secrets outside Git. Never commit Firebase JSON, Moodle tokens or bearer tokens.
3. Start MongoDB as a replica set. Unit tests use isolated databases; integration tests require `RUN_MONGO_INTEGRATION=1`.
4. Run `py scripts/verify_baseline.py` from the repository root, then backend tests, frontend tests/lint/build.
5. Acceptance uses `INFERENCE_POLICY=LOCAL_ONLY` and an explicit `LOCAL_INFERENCE_ALLOWED_HOSTS` list.

## Gate status

- Gate A — technical baseline and contracts: **CLOSED on 2026-09-06**. Requirements,
  runtime, data manifest, rubric/split contract and Moodle boundary are explicit and reproducible.
- Gate B — authorization, export and invariants: **CLOSED on 2026-09-06**. The pinned
  Python 3.10.14 suite passed 180 tests (4 integration tests are separately gated), all
  4 Mongo replica-set integration tests passed, and the frontend passed 46 tests, lint
  and production build.
- Gate C — trustworthy source and durable document processing: **IMPLEMENTED, pending
  pilot-corpus sign-off on 2026-09-06**. PDF processing is extraction-first per page with
  OCR fallback and resource limits; raw/layout/visual evidence is retained in immutable
  processing revisions; corrections create a new page set; OCR/chunk/index jobs use the
  Mongo worker lease/fencing path; index candidates are activated only after coverage
  validation. The code-level suite passed 189 tests plus 9 isolated replica-set
  integration tests; frontend passed 46 tests, lint and production build. T01–T03 on the
  licensed CTDL corpus remain external evidence and are not claimed by this technical gate.
- Gate D — retrieval and prompt/model release: **IMPLEMENTED, pending licensed-corpus
  benchmark on 2026-09-06**. Independent dense/lexical retrieval, hard chapter scope,
  token-budgeted context, retrieval traces, index switch/rollback manifests, strict prompt
  releases, prompt preview, local model roles and structured output are covered by 197 backend
  tests plus 9 replica-set integration tests; frontend passed 46 tests, lint and build. G4 recall@5
  remains unclaimed until the licensed, expert-labelled CTDL query set is supplied and the
  reproducible benchmark report meets the predefined 0.85 target.
- Gate E — question quality, evaluator and HITL: **IMPLEMENTED, pending expert calibration
  on 2026-09-06**. Seven question types share one typed contract; AI evidence is persisted as
  verified quote/page/character spans; evaluator input is token-budgeted and records no-data,
  hard failures, policy/input/model fingerprints and server-side aggregation. C/C++ snippets use
  a syntax-only constrained sandbox with a toolchain snapshot. Generation retries resume from
  per-plan checkpoints and expose partial results. The code-level suite passed 208 tests and the
  frontend passed 47 tests, lint and build. G5/G6/G7 remain external until the licensed CTDL
  golden set and independent reviewers produce grounding, Bloom/CLO and inter-rater evidence.
- Gate F — blueprint, finalized exams and paper variants: **IMPLEMENTED, pending educator and
  rendered-artifact QA on 2026-09-06**. Blueprint V2 preserves Bloom 1–6 and adds CLO/type/marks;
  shared eligibility, overlap allocation, coverage validation, CAS finalization, immutable checksummed
  snapshots, typed deterministic shuffling and export manifests are covered by 212 backend tests.
  Frontend passed 47 tests, lint and build. G8 remains external until an educator uses a real bank and
  every PDF/DOCX page containing code, formulas, images and tables is visually inspected.
- Gate G — Moodle identity and verified Question Bank publication: **IMPLEMENTED, pending real
  institutional target on 2026-09-06**. The seven-type serializer/capability matrix, external-ID
  sync with verified links/checkpoints/revocation, REST adapter, idempotent outbox, UNKNOWN
  reconciliation and admin controls are covered by 222 backend tests; frontend passed 47 tests,
  lint and build. No remote success is claimed until the institution supplies the Moodle build,
  plugin, scoped service account/course/category and round-trip fixtures and verify-read succeeds.
- Migration rehearsal: **PASSED** on isolated Mongo database copies. Membership backfill
  produced one membership on first apply and zero changes on the second apply, with no
  duplicates; bearer sanitization reduced persisted raw bearer records from one to zero.
- Institutional validation remains external: licensed CTDL corpus/expert labels and the
  real Moodle version, service-account capabilities, course/category and round-trip
  fixture. These do not reopen A/B implementation; they are required evidence for the
  dependent quality and Moodle gates (E/G/H).
