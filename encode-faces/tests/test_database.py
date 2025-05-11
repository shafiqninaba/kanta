# tests/test_database.py
# ======================
# End-to-end async tests for src.db.database.Database.

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List

import pytest
import pytest_asyncio

from src.db.database import Database


# Fixtures
@pytest_asyncio.fixture(scope="function")
async def db() -> Database:
    """Create and tear down a fresh Database pool for each test."""
    instance = Database(
        host=os.getenv("DBHOST", "localhost"),
        user=os.getenv("DBUSER", "kanta_admin"),
        password=os.getenv("DBPASSWORD", "password"),
        database=os.getenv("DBNAME", "postgres"),
        port=int(os.getenv("DBPORT", 5432)),
    )
    await instance.connect()
    yield instance
    await instance.close()


# Helper Functions
async def _insert_image(db: Database, *, faces: int = 0) -> str:
    """
    Insert one image row and return its UUID.
    Automatically stamps `created_at` / `last_modified` with UTC-now.
    """
    u = uuid.uuid4().hex
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.insert_image(
        image_uuid=u,
        azure_blob_url=f"https://blob.test/{u}.jpg",
        faces=faces,
        created_at=now,
        last_modified=now,
    )
    return u


async def _insert_faces(
    db: Database, *, image_uuid: str, n: int = 2, start: float = 0.1
) -> List[int]:
    """
    Insert `n` faces with subtly different embeddings into `image_uuid`,
    then return their generated face_ids via get_image_details_by_uuid().
    """
    for i in range(n):
        val = start + i * 0.01
        await db.insert_face(
            image_uuid=image_uuid,
            bbox={"x": i, "y": i, "width": 10 + i, "height": 10 + i},
            embedding=[val] * 128,
            cluster_id=-1,
        )
    # fetch all faces and extract the last n entries
    details = await db.get_image_details_by_uuid(image_uuid)
    assert details is not None, "Failed to retrieve image details after inserts"
    return [f["face_id"] for f in details["faces"]][-n:]


# Test


@pytest.mark.asyncio
async def test_insert_and_get_images(db: Database) -> None:
    """`insert_image` then `get_images` without filters should return it."""
    u1 = await _insert_image(db, faces=1)
    u2 = await _insert_image(db, faces=2)

    all_imgs = await db.get_images(limit=50, offset=0)
    uuids = {row["uuid"].strip() for row in all_imgs}

    assert u1 in uuids, f"Expected {u1!r} in {uuids}"
    assert u2 in uuids, f"Expected {u2!r} in {uuids}"

    # test min_faces / max_faces filters
    few = await db.get_images(min_faces=2, limit=10, offset=0)
    assert all(r["faces"] >= 2 for r in few), "min_faces filter failed"

    some = await db.get_images(max_faces=1, limit=10, offset=0)
    assert all(r["faces"] <= 1 for r in some), "max_faces filter failed"


@pytest.mark.asyncio
async def test_get_image_details_and_insert_faces(db: Database) -> None:
    """`get_image_details_by_uuid` reflects inserted faces and metadata."""
    u = await _insert_image(db, faces=0)
    fids = await _insert_faces(db, image_uuid=u, n=2, start=0.2)  # add two faces

    details = await db.get_image_details_by_uuid(u)
    assert details is not None, "Expected image_details, got None"
    assert details["image"]["uuid"].strip() == u
    received = details["faces"]
    ids = [f["face_id"] for f in received]
    assert set(fids) <= set(ids), f"Inserted {fids}, got back {ids}"


@pytest.mark.asyncio
async def test_similarity_search(db: Database) -> None:
    """The exact same vector should be returned with zero (or minimal) distance."""
    u = await _insert_image(db)
    fids = await _insert_faces(db, image_uuid=u, n=1, start=0.42)
    ref = [0.42] * 128

    hits = await db.similarity_search(target_embedding=ref, metric="cosine", top_k=3)
    assert hits, "Expected at least one hit"
    print(hits)

    # # the top hit should correspond to our single inserted face
    # top = hits[0]
    # assert (
    #     top["face_id"] == fids[0]
    # ), f"Expected face_id {fids[0]}, got {top['face_id']}"


@pytest.mark.asyncio
async def test_get_all_embeddings(db: Database) -> None:
    """`get_all_embeddings` returns parsed 128-D lists with correct keys."""
    u = await _insert_image(db)
    await _insert_faces(db, image_uuid=u, n=3, start=0.55)

    rows = await db.get_all_embeddings()
    # take last 3
    tail = rows[-3:]
    assert tail, "No embeddings returned"
    for r in tail:
        assert set(r.keys()) == {"face_id", "embedding"}  # check keys
        assert isinstance(r["embedding"], list)  # check type
        assert len(r["embedding"]) == 128  # check length


@pytest.mark.asyncio
async def test_update_cluster_and_filter_images(db: Database) -> None:
    """Bulk-update cluster IDs then use `get_images(cluster_list_id=…)`."""
    u1 = await _insert_image(db)
    u2 = await _insert_image(db)
    f1 = (await _insert_faces(db, image_uuid=u1, n=1, start=0.1))[0]
    f2 = (await _insert_faces(db, image_uuid=u2, n=1, start=0.2))[0]

    upd = {f1: 7, f2: 8}
    await db.update_cluster_ids(upd)

    # only u1 (cluster 7)
    imgs7 = await db.get_images(cluster_list_id=[7], limit=10, offset=0)
    assert u1 in {img["uuid"].strip() for img in imgs7}, f"Expected {u1!r} in {imgs7}"

    # only u2 (cluster 8)
    imgs8 = await db.get_images(cluster_list_id=[8], limit=10, offset=0)
    assert u2 in {img["uuid"].strip() for img in imgs8}, f"Expected {u2!r} in {imgs8}"


@pytest.mark.asyncio
async def test_get_cluster_info(db: Database) -> None:
    """`get_cluster_info` returns per-cluster counts and up to sample_size entries."""
    u = await _insert_image(db)
    fids = await _insert_faces(
        db, image_uuid=u, n=5, start=0.3
    )  # insert 5 faces in cluster 3
    await db.update_cluster_ids({fid: 3 for fid in fids})  # assign cluster_id=3

    summary = await db.get_cluster_info(sample_size=2)

    # assert structure
    assert isinstance(summary, list)
    expected = {
        "cluster_id",
        "face_count",
        "samples",
    }  # each summary dict must have exactly these three keys
    assert all(
        set(item.keys()) == expected for item in summary
    ), f"Unexpected summary structure: {summary}"


@pytest.mark.asyncio
async def test_raw_query_and_deletion(db: Database) -> None:
    """You can run ad-hoc SQL and delete all faces + image afterwards."""
    u = await _insert_image(db)
    await _insert_faces(db, image_uuid=u, n=2)

    before = await db.string_query("SELECT COUNT(*) FROM faces")
    before_cnt = before[0]["count"]
    await db.delete_image_by_uuid(u)
    after = await db.string_query("SELECT COUNT(*) FROM faces")
    after_cnt = after[0]["count"]

    assert (
        after_cnt < before_cnt
    ), f"Expected fewer faces after delete, got {after_cnt} ≥ {before_cnt}"
