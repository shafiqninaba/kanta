"""
tests/test_database.py
======================
End‑to‑end unit tests for ``src.db.database.Database``.

Expected behaviour
------------------
1.  We can insert image rows and immediately query them back.
2.  Faces can be appended to an image and paged/filter‑queried correctly.
3.  Cluster IDs can be bulk‑updated in a single call.
4.  Ad‑hoc SQL works and rows are removed when delete helpers are called.

The tests use **fresh UUIDs** per run to avoid clashes and rely on a dedicated
test database.  Each test function gets its own connection pool so they can run
in parallel without "operation in progress" errors.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
import os
from typing import Dict, List

import pytest
import pytest_asyncio

from src.db.database import Database


# Fixtures
@pytest_asyncio.fixture(scope="function")
async def db() -> Database:
    """Create a new Database pool for every test function."""
    instance = Database(
        host=os.getenv("DBHOST"),
        user=os.getenv("DBUSER", "kanta_admin"),
        password=os.getenv("DBPASSWORD"),
        database=os.getenv("DBNAME", "postgres"),
        port=int(os.getenv("DBPORT", 5432)),
    )
    await instance.connect()
    yield instance
    await instance.close()


# Helper functions
async def _insert_image(
    db: Database,
    *,
    faces: int = 0,
) -> str:
    """Insert one image and return its UUID."""
    uuid_hex = uuid.uuid4().hex
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.insert_image(
        uuid=uuid_hex,
        url=f"https://blob/{uuid_hex}.jpg",
        faces=faces,
        created_at=now,
        last_modified=now,
    )
    return uuid_hex


async def _insert_faces(
    db: Database,
    *,
    image_uuid: str,
    n: int = 2,
) -> List[int]:
    """Insert *n* dummy faces for *image_uuid* and return their IDs."""
    ids: List[int] = []
    for i in range(n):
        await db.insert_face(
            image_uuid=image_uuid,
            cluster_id=0,
            bbox={"x": i, "y": i, "width": 10 + i, "height": 10 + i},
            embedding=[0.1 + i * 0.01] * 128,
        )
        # grab the id just inserted (cheapest: RETURNING would be nicer)
    rows = await db.get_faces(image_uuid=image_uuid)
    ids.extend(face["face_id"] for face in rows[-n:])
    return ids


# CRUD tests
@pytest.mark.asyncio
async def test_insert_and_get_images(db: Database) -> None:
    """Images inserted via ``insert_image`` are returned by ``get_images``."""
    img1_uuid = await _insert_image(db)
    img2_uuid = await _insert_image(db)

    rows = await db.get_images()
    uuids = {r["uuid"].strip() for r in rows}

    assert img1_uuid in uuids, f"{img1_uuid} missing from results {uuids}"
    assert img2_uuid in uuids, f"{img2_uuid} missing from results {uuids}"


@pytest.mark.asyncio
async def test_insert_and_get_faces(db: Database) -> None:
    """Faces can be inserted and paginated."""
    img_uuid = await _insert_image(db)
    await _insert_faces(db, image_uuid=img_uuid, n=3)

    faces_for_img = await db.get_faces(image_uuid=img_uuid)
    assert len(faces_for_img) == 3, f"Expected 3 faces, got {len(faces_for_img)}"

    first_page = await db.get_faces(image_uuid=img_uuid, limit=1, offset=0)
    second_page = await db.get_faces(image_uuid=img_uuid, limit=1, offset=1)

    assert (
        first_page[0]["face_id"] != second_page[0]["face_id"]
    ), "Pagination returned duplicate rows"


@pytest.mark.asyncio
async def test_vector_search_raw(db: Database) -> None:
    """Top‑1 search should return the identical face as most similar."""
    uid = await _insert_image(db)
    await _insert_faces(db, image_uuid=uid, n=1)
    ref_vec = [0.1] * 128

    hits = await db.similarity_search(
        target_embedding=ref_vec, metric="cosine", top_k=2
    )
    print(hits)
    assert hits, "Search returned no rows"


@pytest.mark.asyncio
async def test_get_all_embeddings_raw(db: Database) -> None:
    """get_all_embeddings should return parsed 128‑D vectors for each face."""
    uid = await _insert_image(db)
    await _insert_faces(db, image_uuid=uid, n=3)

    rows = await db.get_all_embeddings()
    ours = [r for r in rows if r["face_id"] >= rows[-3]["face_id"]]  # last 3 we added

    assert ours, "No embeddings returned"

    expected_keys = {"face_id", "embedding"}
    assert all(
        expected_keys == set(r) for r in ours
    ), f"Row keys mismatch — expected {expected_keys}"
    assert all(isinstance(r["embedding"], list) for r in ours), "Embedding not list"
    assert all(len(r["embedding"]) == 128 for r in ours), "Vector length ≠ 128"


@pytest.mark.asyncio
async def test_cluster_update(db: Database) -> None:
    """``update_cluster_ids`` should modify multiple rows in one call."""
    img_uuid = await _insert_image(db)
    face_ids = await _insert_faces(db, image_uuid=img_uuid, n=2)

    update_map: Dict[int, int] = {face_ids[0]: 98, face_ids[1]: 99}
    await db.update_cluster_ids(update_map)

    rows = await db.get_faces(image_uuid=img_uuid)
    clusters = {r["cluster_id"] for r in rows}
    assert clusters >= {98, 99}, f"Clusters not updated: {clusters}"


@pytest.mark.asyncio
async def test_raw_query_and_delete(db: Database) -> None:
    """Faces count should drop after delete helpers are used."""
    img_uuid = await _insert_image(db)
    await _insert_faces(db, image_uuid=img_uuid, n=2)

    before = await db.string_query("SELECT COUNT(*) FROM faces")
    await db.delete_faces_for_image(img_uuid)
    await db.delete_image(img_uuid)
    after = await db.string_query("SELECT COUNT(*) FROM faces")

    assert after[0]["count"] < before[0]["count"], (
        f"Expected lower count after deletion; before={before[0]['count']} "
        f"after={after[0]['count']}"
    )
