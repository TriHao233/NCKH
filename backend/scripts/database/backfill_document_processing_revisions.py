"""Backfill immutable processing revisions for legacy document page sets.

Dry-run is the default. Use ``--apply`` only after reviewing the summary.
The migration is idempotent: an OCR job/page-set identifier is also the
legacy revision identifier, so reruns do not duplicate records.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bson import ObjectId

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.database import get_database, ping_database
from modules.documents.repository import MongoDocumentRepository, utc_now


def backfill(*, apply: bool = False) -> dict[str, int]:
    db = get_database()
    scanned = revisions = pages = documents = 0
    for document in db.documents.find({"archived_at": None}):
        scanned += 1
        page_sets = list(
            db.document_pages.aggregate(
                [
                    {"$match": {"document_id": document["_id"]}},
                    {
                        "$group": {
                            "_id": "$ocr_job_id",
                            "created_at": {"$min": "$created_at"},
                        }
                    },
                    {"$sort": {"created_at": 1}},
                ]
            )
        )
        active_job_id = (document.get("current_processing") or {}).get("ocr_job_id")
        for revision_no, page_set in enumerate(page_sets, start=1):
            source_job_id = page_set.get("_id") or ObjectId()
            if db.document_processing_revisions.find_one({"_id": source_job_id}):
                continue
            page_records = list(
                db.document_pages.find(
                    {"document_id": document["_id"], "ocr_job_id": page_set.get("_id")}
                ).sort("page_number", 1)
            )
            revisions += 1
            pages += len(page_records)
            if not apply:
                continue
            now = utc_now()
            page_set_hash = MongoDocumentRepository._page_set_hash(page_records)
            db.document_processing_revisions.insert_one(
                {
                    "_id": source_job_id,
                    "schema_version": SCHEMA_VERSION,
                    "document_id": document["_id"],
                    "document_version": page_records[0].get("document_version", 1)
                    if page_records
                    else document.get("current_version", 1),
                    "revision_no": revision_no,
                    "source_job_id": source_job_id,
                    "parent_revision_id": page_sets[revision_no - 2].get("_id")
                    if revision_no > 1
                    else None,
                    "kind": "LEGACY_OCR",
                    "status": "ACTIVE" if source_job_id == active_job_id else "SUPERSEDED",
                    "page_count": len(page_records),
                    "page_set_hash": page_set_hash,
                    "manifest": {"migrated_from_legacy": True},
                    "created_at": page_set.get("created_at") or now,
                    "completed_at": now,
                }
            )
            db.document_pages.update_many(
                {"document_id": document["_id"], "ocr_job_id": page_set.get("_id")},
                {
                    "$set": {
                        "processing_revision_id": source_job_id,
                        "revision_no": revision_no,
                        "updated_at": now,
                    }
                },
            )
            db.document_jobs.update_one(
                {"_id": source_job_id},
                {"$set": {"processing_revision_id": source_job_id}},
            )
        if active_job_id and not (document.get("current_processing") or {}).get(
            "processing_revision_id"
        ):
            documents += 1
            if apply:
                db.documents.update_one(
                    {"_id": document["_id"], "current_processing.ocr_job_id": active_job_id},
                    {
                        "$set": {
                            "current_processing.processing_revision_id": active_job_id,
                            "current_processing.pending_ocr_job_id": None,
                            "current_processing.pending_processing_revision_id": None,
                            "updated_at": utc_now(),
                        }
                    },
                )
    return {
        "documents_scanned": scanned,
        "revisions_to_create": revisions,
        "pages_to_tag": pages,
        "documents_to_update": documents,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    ping_database()
    bootstrap_database()
    result = backfill(apply=args.apply)
    print({"mode": "apply" if args.apply else "dry-run", **result})


if __name__ == "__main__":
    main()
