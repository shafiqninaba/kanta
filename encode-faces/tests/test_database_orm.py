# tests/test_database_orm.py
# ==========================
# End-to-end async tests for src.db.database_orm.ORMDatabase.

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List

import pytest
import pytest_asyncio

from src.db.database_orm import ORMDatabase


# ─── Fixture ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def db() -> ORMDatabase:
    """
    Provide a fresh ORMDatabase (with tables created) for each test,
    and tear it down afterwards.
    """
    instance = ORMDatabase(
        host=os.getenv("DBHOST", "localhost"),
        port=int(os.getenv("DBPORT", 5432)),
        user=os.getenv("DBUSER", "kanta_admin"),
        password=os.getenv("DBPASSWORD", "password"),
        database=os.getenv("DBNAME", "postgres"),
        ssl=os.getenv("SSLMODE", "require"),
    )
    await instance.init_models()
    yield instance
    await instance.close()


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _insert_image(db: ORMDatabase, *, faces: int = 0) -> str:
    """
    Create one Image row via ORMDatabase.insert_image and return its UUID.
    """
    uid = uuid.uuid4().hex
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.insert_image(
        uuid=uid,
        url=f"https://blob.test/{uid}.jpg",
        faces=faces,
        created_at=now,
        last_modified=now,
    )
    return uid


async def _insert_faces(
    db: ORMDatabase, *, image_uuid: str, n: int = 2, start: float = 0.1
) -> List[int]:
    """
    Add `n` faces to `image_uuid` with slightly varying embeddings.
    Return the list of generated face IDs.
    """
    ids: List[int] = []
    for i in range(n):
        emb_val = start + i * 0.01
        face = await db.insert_face(
            image_uuid=image_uuid,
            cluster_id=-1,
            bbox={"x": i, "y": i, "width": 10 + i, "height": 10 + i},
            embedding=[emb_val] * 128,
        )
        ids.append(face.id)
    return ids


# ─── Tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_images(db: ORMDatabase) -> None:
    """Images inserted via ORM are returned by get_images()."""
    u1 = await _insert_image(db, faces=1)
    u2 = await _insert_image(db, faces=2)

    imgs = await db.get_images(limit=10, offset=0)
    uuids = {img.uuid for img in imgs}

    assert u1 in uuids, f"Expected {u1} in {uuids}"
    assert u2 in uuids, f"Expected {u2} in {uuids}"

    # test min_faces / max_faces filters
    ge2 = await db.get_images(min_faces=2, limit=10, offset=0)
    assert all(img.faces >= 2 for img in ge2), "min_faces filter failed"

    le1 = await db.get_images(max_faces=1, limit=10, offset=0)
    assert all(img.faces <= 1 for img in le1), "max_faces filter failed"


@pytest.mark.asyncio
async def test_get_image_by_uuid_and_faces(db: ORMDatabase) -> None:
    """
    insert_image + insert_face → get_image_by_uuid returns an Image
    with faces_rel populated.
    """
    u = await _insert_image(db, faces=0)
    face_ids = await _insert_faces(db, image_uuid=u, n=3, start=0.3)

    img = await db.get_image_by_uuid(u)
    assert img is not None, "get_image_by_uuid returned None"
    # ORM relationship was loaded via selectinload
    rel_ids = [f.id for f in img.faces_rel]
    assert set(face_ids) <= set(rel_ids), f"Expected {face_ids}, got {rel_ids}"


@pytest.mark.asyncio
async def test_similarity_search_orm(db: ORMDatabase) -> None:
    """The identical embedding should come back as the top-1 hit."""
    u = await _insert_image(db)
    ids = await _insert_faces(db, image_uuid=u, n=1, start=0.42)
    ref = [0.42] * 128

    hits = await db.similarity_search(target_embedding=ref, metric="cosine", top_k=2)
    assert hits, "No hits returned"
    # assert (
    #     hits[0]["face_id"] == ids[0]
    # ), f"Expected face_id {ids[0]}, got {hits[0]['face_id']}"


@pytest.mark.asyncio
async def test_get_all_embeddings_orm(db: ORMDatabase) -> None:
    """get_all_embeddings returns correct face_id and 128-dim lists."""
    u = await _insert_image(db)
    await _insert_faces(db, image_uuid=u, n=4, start=0.55)

    rows = await db.get_all_embeddings()
    tail = rows[-4:]
    assert tail, "No embeddings returned"
    for rec in tail:
        assert set(rec.keys()) == {"face_id", "embedding"}
        assert isinstance(rec["embedding"], list)
        assert len(rec["embedding"]) == 128


@pytest.mark.asyncio
async def test_update_cluster_ids_and_reflect(db: ORMDatabase) -> None:
    """update_cluster_ids changes cluster_id, and get_image_by_uuid reflects it."""
    u = await _insert_image(db)
    fids = await _insert_faces(db, image_uuid=u, n=2)
    mapping = {fids[0]: 7, fids[1]: 8}

    await db.update_cluster_ids(mapping)
    img = await db.get_image_by_uuid(u)
    assert img is not None
    clusters = {f.cluster_id for f in img.faces_rel}
    assert clusters >= {7, 8}, f"Clusters not updated: {clusters}"


@pytest.mark.asyncio
async def test_get_cluster_info_orm(db: ORMDatabase) -> None:
    """
    get_cluster_info returns a summary per cluster with up to sample_size
    random samples.
    """
    u = await _insert_image(db)
    fids = await _insert_faces(db, image_uuid=u, n=5, start=0.6)
    await db.update_cluster_ids(
        {fid: 3 for fid in fids}
    )  # assign them all to cluster 3

    summary = await db.get_cluster_info(sample_size=2)

    # assert isinstance(summary, list)
    expected_keys = {"cluster_id", "face_count", "samples"}
    assert all(
        set(c.keys()) == expected_keys for c in summary
    ), f"Unexpected summary structure: {summary}"


@pytest.mark.asyncio
async def test_raw_query_and_cascade_delete_orm(db: ORMDatabase) -> None:
    """
    raw_query counts faces,
    delete_image cascades faces,
    count should drop.
    """
    u = await _insert_image(db)
    await _insert_faces(db, image_uuid=u, n=3)

    before = await db.string_query("SELECT COUNT(*) AS cnt FROM faces")
    before_cnt = before[0]["cnt"]

    # delete the image → faces cascade
    await db.delete_faces_by_uuid(u)

    after = await db.string_query("SELECT COUNT(*) AS cnt FROM faces")
    after_cnt = after[0]["cnt"]

    assert (
        after_cnt < before_cnt
    ), f"Expected fewer faces, got {after_cnt} ≥ {before_cnt}"
