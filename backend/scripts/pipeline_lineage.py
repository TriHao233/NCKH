from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from modules.rag.lineage import CandidateLineage, LineagePromotionService, LineageValidator


def _candidate(args) -> CandidateLineage:
    required = (args.document_id, args.ocr_job_id, args.chunk_set_id, args.vector_collection_id)
    if not all(required):
        raise ValueError("document/ocr-job/chunk-set/vector-collection IDs are required")
    return CandidateLineage(*required)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and operate versioned OCR/RAG lineage")
    parser.add_argument("action", choices=("validate", "dry-run", "promote", "rollback", "archive", "delete-request", "delete-execute"))
    parser.add_argument("--document-id")
    parser.add_argument("--ocr-job-id")
    parser.add_argument("--chunk-set-id")
    parser.add_argument("--vector-collection-id")
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--actor")
    parser.add_argument("--reason")
    parser.add_argument("--confirm")
    parser.add_argument("--operation-id")
    args = parser.parse_args()
    service = LineagePromotionService()
    if args.action == "validate":
        result = LineageValidator().validate(_candidate(args), smoke_queries=args.query)
    elif args.action == "dry-run":
        result = service.dry_run(_candidate(args), smoke_queries=args.query)
    elif args.action == "promote":
        result = service.promote(
            _candidate(args), smoke_queries=args.query, actor=args.actor or "", reason=args.reason or "", confirmation=args.confirm or ""
        )
    elif args.action == "rollback":
        result = service.rollback(args.operation_id or "", actor=args.actor or "", reason=args.reason or "")
    elif args.action == "archive":
        result = service.archive(_candidate(args), actor=args.actor or "", reason=args.reason or "")
    elif args.action == "delete-request":
        result = service.request_permanent_delete(
            _candidate(args), actor=args.actor or "", reason=args.reason or "", confirmation=args.confirm or ""
        )
    else:
        result = service.execute_permanent_delete(args.operation_id or "", confirmation=args.confirm or "")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") not in {"failed", "needs_review"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
