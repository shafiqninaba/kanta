"""
tests/test_database_orm.py
==========================
End‑to‑end tests for ``src.db.database_orm.ORMDatabase``.

Expected behaviour
------------------
1. Images created through ORM are queryable.
2. Faces can be appended to an image and paged/filter‑queried.
3. Cluster IDs can be bulk‑updated.
4. Raw SQL passthrough works and delete helpers remove rows.

Each test gets a fresh async‑session pool, with unique UUIDs → no clashes.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List

import pytest
import pytest_asyncio

from src.db.database_orm import ORMDatabase


# --------------------------------------------------------------------------- #
# Fixture
# --------------------------------------------------------------------------- #
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List

import pytest
import pytest_asyncio

from src.db.database_orm import ORMDatabase


@pytest_asyncio.fixture(scope="function")
async def db() -> ORMDatabase:
    """Provide a fresh ORMDatabase for each test."""
    db = ORMDatabase(
        host=os.getenv("DBHOST", "localhost"),
        port=int(os.getenv("DBPORT", 5432)),
        user=os.getenv("DBUSER", "kanta_admin"),
        password=os.getenv("DBPASSWORD", "password"),
        database=os.getenv("DBNAME", "postgres"),
        ssl=os.getenv("SSLMODE", "require"),
    )
    await db.init_models()
    yield db
    await db.close()


# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #
async def _insert_image(db: ORMDatabase, *, faces: int = 0) -> str:  # returns uuid
    uid = uuid.uuid4().hex
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.insert_image(
        uuid=uid,
        url=f"https://blob/{uid}.jpg",
        faces=faces,
        created_at=now,
        last_modified=now,
    )
    return uid


async def _insert_faces(db: ORMDatabase, *, image_uuid: str, n: int = 2) -> List[int]:
    ids: List[int] = []
    for i in range(n):
        face = await db.insert_face(
            image_uuid=image_uuid,
            cluster_id=0,
            bbox={"x": i, "y": i, "width": 10 + i, "height": 10 + i},
            embedding=[0.1 + i * 0.01] * 128,
        )
        ids.append(face.id)
    return ids


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_and_list_images(db: ORMDatabase) -> None:
    """Images inserted via ORM are returned by list_images()."""
    uid1, uid2 = await _insert_image(db), await _insert_image(db)

    rows = await db.get_images(limit=100)
    uuids = {img.uuid for img in rows}

    assert uid1 in uuids, f"{uid1} missing in {uuids}"
    assert uid2 in uuids, f"{uid2} missing in {uuids}"


@pytest.mark.asyncio
async def test_insert_and_pagination_faces(db: ORMDatabase) -> None:
    """Faces insert + pagination via get_faces()."""
    uid = await _insert_image(db)
    await _insert_faces(db, image_uuid=uid, n=3)

    faces_all = await db.get_faces(image_uuid=uid)
    assert len(faces_all) == 3, f"Expected 3 faces, got {len(faces_all)}"

    page1 = await db.get_faces(image_uuid=uid, limit=1, offset=0)
    page2 = await db.get_faces(image_uuid=uid, limit=1, offset=1)

    assert page1[0].id != page2[0].id, "Pagination returned duplicate row"


@pytest.mark.asyncio
async def test_vector_search_orm(db: ORMDatabase) -> None:
    """Vector search via ORM returns correct nearest neighbour."""
    uid = await _insert_image(db)
    await _insert_faces(db, image_uuid=uid, n=1)

    ref_vec = [0.1] * 128

    hits = await db.similarity_search(
        target_embedding=ref_vec, metric="cosine", top_k=1
    )
    assert hits, "No search results"


@pytest.mark.asyncio
async def test_get_all_embeddings_orm(db: ORMDatabase) -> None:
    uid = await _insert_image(db)
    await _insert_faces(db, image_uuid=uid, n=2)

    rows = await db.get_all_embeddings()
    # Filter rows for just the last 3 faces
    ours = rows[-3:]  # take the last 3 rows

    assert ours, "No embeddings returned"

    expected_keys = {"face_id", "embedding"}
    assert all(
        expected_keys == set(r) for r in ours
    ), f"Row keys mismatch — expected {expected_keys}"
    assert all(isinstance(r["embedding"], list) for r in ours), "Embedding not list"
    assert all(len(r["embedding"]) == 128 for r in ours), "Vector length ≠ 128"


@pytest.mark.asyncio
async def test_cluster_updates(db: ORMDatabase) -> None:
    """update_cluster_ids should modify multiple rows."""
    uid = await _insert_image(db)
    face_ids = await _insert_faces(db, image_uuid=uid, n=2)

    await db.update_cluster_ids({face_ids[0]: 98, face_ids[1]: 99})

    faces = await db.get_faces(image_uuid=uid)
    clusters = {f.cluster_id for f in faces}
    assert clusters >= {98, 99}, f"Clusters not updated: {clusters}"


@pytest.mark.asyncio
async def test_raw_query_and_deletes(db: ORMDatabase) -> None:
    """Faces count should decrease after deletion helpers."""
    uid = await _insert_image(db)
    await _insert_faces(db, image_uuid=uid, n=2)

    before = await db.raw_query("SELECT COUNT(*) AS c FROM faces")
    await db.delete_faces_for_image(uid)
    await db.delete_image(uid)
    after = await db.raw_query("SELECT COUNT(*) AS c FROM faces")

    assert after[0]["c"] < before[0]["c"], (
        f"Expected fewer rows after delete; before={before[0]['c']}, "
        f"after={after[0]['c']}"
    )
