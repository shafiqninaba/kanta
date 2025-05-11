# Updated `database.py` to match new schema (with image_id FK, vector type for embeddings)

"""
database.py
===========
Async PostgreSQL helper for **images** and **faces** tables.

This module provides a high-level interface to the *images* and *faces* tables
in a PostgreSQL database hosted on Azure, using the `asyncpg` library.

It manages a connection pool and executes SQL queries asynchronously using Python's
`asyncio` event loop. This is ideal for scalable applications where non-blocking
database operations are critical.

The schema includes:
- `images`: image metadata (UUID, blob URL, timestamps, file extension)
- `faces`: face metadata and embeddings linked to an image

Note: All SQL is raw. Use `string_query()` for ad-hoc queries.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg


class Database:
    """Async interface for interacting with the *images* and *faces* PostgreSQL schema."""

    def __init__(
        self,
        *,
        host: str,
        password: str,
        port: int = 5432,
        user: str = "admin",
        database: str = "postgres",
        ssl: str | asyncpg.SSLContext = "require",
        min_size: int = 1,
        max_size: int = 5,
    ) -> None:
        """Store connection parameters for use in asyncpg's connection pool.

        Args:
            host: PostgreSQL host (Azure hostname or IP).
            password: PostgreSQL password.
            port: PostgreSQL port (default: 5432).
            user: PostgreSQL user (default: "admin").
            database: Database name (default: "postgres").
            ssl: SSL mode or context (default: "require").
            min_size: Minimum pool size (default: 1).
            max_size: Maximum pool size (default: 5).
        """
        for k, v in {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }.items():
            if v is None:
                raise ValueError(f"{k} is required")

        self._kw = dict(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            ssl=ssl,
            min_size=min_size,
            max_size=max_size,
        )
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Create the asyncpg connection pool (idempotent).

        Avoids opening a new TLS session per query by reusing pooled connections.
        """
        if self._pool:
            return
        try:
            self._pool = await asyncpg.create_pool(**self._kw)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect: {exc}") from exc

    async def close(self) -> None:
        """Close and release the asyncpg connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def string_query(self, sql: str, *params: Any) -> List[asyncpg.Record]:
        """Execute arbitrary SQL using raw string with parameter placeholders.

        Args:
            sql: Query string with `$1` … `$n` placeholders.
            *params: Values to bind to placeholders.

        Returns:
            List of asyncpg.Record rows.

        Raises:
            RuntimeError: If pool is uninitialised or query fails.
        """
        if not self._pool:
            raise RuntimeError("Pool not initialised; call connect() first")
        try:
            async with self._pool.acquire() as conn:
                return await conn.fetch(sql, *params)
        except Exception as exc:
            raise RuntimeError(f"string_query failed: {exc}") from exc

    # Images
    # ======================================================================

    async def insert_image(
        self,
        uuid: str,
        url: str,
        faces: int,
        created_at: datetime,
        last_modified: datetime,
    ) -> None:
        """Insert a new row into the `images` table.

        Args:
            uuid: 32-character UUID string (no dashes).
            url: Azure blob storage URL for the image.
            faces: Number of detected faces.
            created_at: Timestamp when image was created.
            last_modified: Timestamp when image was last modified.
        """
        await self.string_query(
            """
            INSERT INTO images(uuid, azure_blob_url, faces, created_at, last_modified)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT (uuid) DO NOTHING
            """,
            uuid,
            url,
            faces,
            created_at,
            last_modified,
        )

    async def delete_image(self, uuid: str) -> None:
        """Delete an image and all associated faces (via ON DELETE CASCADE).

        Args:
            uuid: 32-character UUID of the image.
        """
        await self.string_query("DELETE FROM images WHERE uuid = $1", uuid)

    async def get_images(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        min_faces: Optional[int] = None,
        max_faces: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query a list of images, with optional filters and pagination.

        Args:
            limit: Max number of rows to return (default: 50).
            offset: Number of rows to skip (default: 0).
            date_from: Filter for images created after this date.
            date_to: Filter for images created before this date.
            min_faces: Minimum face count filter.
            max_faces: Maximum face count filter.

        Returns:
            List of image rows as dictionaries.
        """
        clauses: List[str] = []
        params: List[Any] = []

        def _add(sql_cond: str, val: Any) -> None:
            params.append(val)
            clauses.append(f"{sql_cond} ${len(params)}")

        if date_from:
            _add("created_at >=", date_from)
        if date_to:
            _add("created_at <=", date_to)
        if min_faces is not None:
            _add("faces >=", min_faces)
        if max_faces is not None:
            _add("faces <=", max_faces)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])

        rows = await self.string_query(
            f"""
            SELECT uuid, azure_blob_url, file_extension,
                   faces, created_at, last_modified
            FROM images
            {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return [dict(r) for r in rows]

    # Faces
    # ======================================================================

    async def insert_face(
        self,
        image_uuid: str,
        cluster_id: int,
        bbox: Dict[str, int],
        embedding: List[float],
    ) -> None:
        """Insert a new face record for the given image UUID.

        Args:
            image_uuid: 32-character UUID of the parent image.
            cluster_id: Assigned cluster ID.
            bbox: Bounding box dictionary with keys "x", "y", "width", "height".
            embedding: 128-dimensional embedding vector.
        """
        # Lookup image_id from image_uuid
        row = await self.string_query(
            "SELECT id FROM images WHERE uuid = $1", image_uuid
        )
        if not row:
            raise ValueError(f"No image found with uuid={image_uuid}")
        image_id = row[0]["id"]

        await self.string_query(
            """
            INSERT INTO faces(image_id, image_uuid, cluster_id, bbox, embedding)
            VALUES($1, $2, $3, $4::jsonb, $5::vector)
            """,
            image_id,
            image_uuid,
            cluster_id,
            json.dumps(bbox),
            f"[{','.join(map(str, embedding))}]",
        )

    async def get_faces(
        self,
        *,
        image_uuid: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch a list of face rows, optionally filtered by image UUID.

        Args:
            image_uuid: Filter faces by a specific image UUID.
            limit: Maximum number of rows (default: 50).
            offset: Number of rows to skip (default: 0).

        Returns:
            List of face rows with image URL and bounding box.
        """
        params: List[Any] = []
        where = ""
        if image_uuid:
            params.append(image_uuid)
            where = "WHERE f.image_uuid = $1"

        params.extend([limit, offset])

        rows = await self.string_query(
            f"""
            SELECT f.id AS face_id,
                   f.image_uuid,
                   i.azure_blob_url,
                   f.cluster_id,
                   f.bbox
            FROM faces AS f
            JOIN images AS i ON i.uuid = f.image_uuid
            {where}
            ORDER BY f.id
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
        return [dict(r) for r in rows]

    async def delete_faces_for_image(self, image_uuid: str) -> None:
        """Delete all face records associated with an image.

        Args:
            image_uuid: UUID of the image.
        """
        await self.string_query("DELETE FROM faces WHERE image_uuid = $1", image_uuid)

    # Vector functions
    # ======================================================================
    async def similarity_search(
        self,
        *,
        target_embedding: Sequence[float],
        metric: str = "cosine",
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return *top_k* most similar faces to `embedding`.

        Args:
            target_embedding: 128‑D reference vector.
            metric:  ``"cosine"``, ``"l2"``, or ``"ip"``.
            top_k:    Maximum rows to return.

        Returns
        -------
        list[dict]
            keys: ``face_id`` • ``image_uuid`` • ``azure_blob_url`` •
                ``cluster_id`` • ``bbox`` • ``embedding`` • ``distance``
        """
        op = {"cosine": "<=>", "l2": "<->", "ip": "<#>"}[metric]
        vec_txt = "[" + ",".join(map(str, target_embedding)) + "]"

        sql = f"""
            SELECT
                f.id        AS face_id,
                f.image_uuid,
                i.azure_blob_url,
                f.cluster_id,
                f.bbox,
                f.embedding::text   AS embedding,
                f.embedding {op} '{vec_txt}'::vector AS distance
            FROM faces AS f
            JOIN images AS i ON i.uuid = f.image_uuid
            ORDER BY distance
            LIMIT $1
            """
        rows = await self.string_query(sql, top_k)

        def _parse(txt: str) -> List[float]:
            return [float(x) for x in txt.strip("[]").split(",")]

        return [
            {
                **dict(r),
                "embedding": _parse(r["embedding"]),
            }
            for r in rows
        ]

    async def get_all_embeddings(self) -> List[Dict[str, Any]]:
        """Return every face‑row embedding as a Python list of floats."""
        rows = await self.string_query(
            "SELECT id AS face_id, embedding::text AS emb FROM faces ORDER BY id"
        )

        def _parse(txt: str) -> List[float]:
            return [float(x) for x in txt.strip("[]").split(",")]

        return [{"face_id": r["face_id"], "embedding": _parse(r["emb"])} for r in rows]

    async def update_cluster_ids(
        self, updates: Dict[int, int] | Sequence[Tuple[int, int]]
    ) -> None:
        """Bulk-update cluster IDs for faces after reclustering.

        Args:
            updates: Dict or list of (face_id, new_cluster_id) tuples.
        """
        pairs = updates.items() if isinstance(updates, dict) else updates
        sql = "UPDATE faces SET cluster_id = $1 WHERE id = $2"
        try:
            async with self._pool.acquire() as conn:  # type: ignore[union-attr]
                await conn.executemany(sql, [(c, fid) for fid, c in pairs])
        except Exception as exc:
            raise RuntimeError(f"update_cluster_ids failed: {exc}") from exc
