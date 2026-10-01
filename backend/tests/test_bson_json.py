from datetime import datetime

from bson import ObjectId

from db.bson_json import restore
from modules.documents.ingest.models import ParseContext, stable_asset_id, stable_block_id
from modules.rag.chromadb_engine import sanitize_metadata_for_chromadb


def test_restore_converts_real_ids_and_timestamps():
    document_id = str(ObjectId())
    restored = restore({
        "_id": document_id,
        "document_id": document_id,
        "subject_ids": [document_id],
        "created_at": "2026-10-01T10:00:00Z",
        "title": document_id,
    })

    assert restored["_id"] == ObjectId(document_id)
    assert restored["document_id"] == ObjectId(document_id)
    assert restored["subject_ids"] == [ObjectId(document_id)]
    assert isinstance(restored["created_at"], datetime)
    assert restored["title"] == document_id


def test_restore_keeps_content_hash_ids_as_strings():
    # stable_block_id / stable_asset_id are 24 hex characters, exactly the shape of an
    # ObjectId. Read back from PostgreSQL they used to become ObjectId and chunking
    # failed with "Object of type ObjectId is not JSON serializable".
    context = ParseContext(
        document_id=str(ObjectId()), source_file_name="tai-lieu.md",
        source_uri="document:test", mime_type="text/markdown", document_type="md",
    )
    block_id = stable_block_id(context, "markdown:1", 0, "Hàng đợi hoạt động theo nguyên tắc FIFO.")
    asset_id = stable_asset_id(context, "markdown:1", 0)
    assert ObjectId.is_valid(block_id) and ObjectId.is_valid(asset_id)

    restored = restore({
        "blocks": [{"block_id": block_id, "asset_ids": [asset_id]}],
        "block_ids": [block_id],
        "assets": [{"asset_id": asset_id}],
    })

    assert restored["blocks"][0]["block_id"] == block_id
    assert restored["blocks"][0]["asset_ids"] == [asset_id]
    assert restored["block_ids"] == [block_id]
    assert restored["assets"][0]["asset_id"] == asset_id


def test_chroma_metadata_tolerates_bson_values_inside_lists():
    oid = ObjectId()

    cleaned = sanitize_metadata_for_chromadb({
        "block_ids": [oid],
        "heading": "Hàng đợi",
        "page_start": 1,
        "empty": None,
    })

    assert cleaned == {"block_ids": f'["{oid}"]', "heading": "Hàng đợi", "page_start": 1}
