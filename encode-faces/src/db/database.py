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

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg


class Database:
    """
    Async interface for interacting with the *images* and *faces* PostgreSQL schema.
    """

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
        """
        Store connection parameters for use in asyncpg's connection pool.

        Args:
            host:     PostgreSQL host (Azure hostname or IP).
            password: PostgreSQL password.
            port:     Port number (default: 5432).
            user:     Username (default: "admin").
            database: Database name (default: "postgres").
            ssl:      SSL mode or context (default: "require").
            min_size: Minimum pool size (default: 1).
            max_size: Maximum pool size (default: 5).

        Raises:
            ValueError: If any required parameter is missing.
        """
        for name, val in {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
        }.items():
            if val is None:
                raise ValueError(f"{name} is required")

        self._kw: Dict[str, Any] = dict(
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
        """
        Create the asyncpg connection pool (idempotent).

        Avoids opening a new TLS session per query by reusing pooled connections.
        """
        if self._pool:
            return
        try:
            self._pool = await asyncpg.create_pool(**self._kw)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect: {exc}") from exc

    async def close(self) -> None:
        """
        Close and release the asyncpg connection pool.
        """
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def string_query(self, sql: str, *params: Any) -> List[asyncpg.Record]:
        """
        Execute arbitrary SQL using raw string with parameter placeholders.

        Args:
            sql:    Query string with `$1` … `$n` placeholders.
            params: Values to bind to placeholders.

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
        image_uuid: str,
        azure_blob_url: str,
        faces: int,
        created_at: datetime,
        last_modified: datetime,
    ) -> None:
        """
        Insert a new row into the `images` table.

        Args:
            image_uuid:     32-character UUID string (no dashes).
            azure_blob_url: Azure Blob Storage URL for the image.
            faces:          Number of detected faces.
            created_at:     Timestamp when the image was created.
            last_modified:  Timestamp when the image was last modified.
        """
        await self.string_query(
            """
            INSERT INTO images(uuid, azure_blob_url, faces, created_at, last_modified)
            VALUES($1, $2, $3, $4, $5)
            ON CONFLICT (uuid) DO NOTHING
            """,
            image_uuid,
            azure_blob_url,
            faces,
            created_at,
            last_modified,
        )

    async def get_images(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        min_faces: Optional[int] = None,
        max_faces: Optional[int] = None,
        cluster_list_id: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query a list of images, with optional filters and pagination.

        Args:
            limit:            Max rows to return (default: 50).
            offset:           Offset (default: 0).
            date_from:        Images created on or after this date.
            date_to:          Images created on or before this date.
            min_faces:        Minimum face count.
            max_faces:        Maximum face count.
            cluster_list_id:  If provided, images having at least one face in these clusters.

        Returns:
            List of image rows as dicts; uses DISTINCT when filtering by cluster.
        """
        params: List[Any] = []
        where_clauses: List[str] = []
        join_cluster = ""

        # cluster filter
        if cluster_list_id:
            params.append(cluster_list_id)
            idx = len(params)
            join_cluster = "JOIN faces AS f2 ON f2.image_uuid = i.uuid"
            where_clauses.append(f"f2.cluster_id = ANY(${idx})")

        def _add(cond: str, val: Any) -> None:
            params.append(val)
            where_clauses.append(f"{cond} ${len(params)}")

        if date_from:
            _add("i.created_at >=", date_from)
        if date_to:
            _add("i.created_at <=", date_to)
        if min_faces is not None:
            _add("i.faces >=", min_faces)
        if max_faces is not None:
            _add("i.faces <=", max_faces)

        # pagination
        params.extend([limit, offset])
        limit_idx, offset_idx = len(params) - 1, len(params)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        sql = f"""
        SELECT DISTINCT
            i.uuid,
            i.azure_blob_url,
            i.faces,
            i.created_at,
            i.last_modified,
            i.file_extension
        FROM images AS i
        {join_cluster}
        {where}
        ORDER BY i.created_at DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
        """

        rows = await self.string_query(sql, *params)
        return [dict(r) for r in rows]

    async def get_image_details_by_uuid(
        self, image_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """
        Return one image’s metadata plus its associated faces.

        Args:
            image_uuid: 32-character UUID of the image.

        Returns:
            {"image": {...}, "faces": [...]}, or None if not found.
        """
        # fetch image row
        rows = await self.string_query(
            """
            SELECT
                uuid,
                azure_blob_url,
                faces,
                created_at,
                last_modified,
                file_extension
            FROM images
            WHERE uuid = $1
            """,
            image_uuid,
        )
        if not rows:
            return None
        image = dict(rows[0])

        # fetch face rows
        face_rows = await self.string_query(
            """
            SELECT
                id        AS face_id,
                image_uuid,
                bbox,
                cluster_id
            FROM faces
            WHERE image_uuid = $1
            ORDER BY id
            """,
            image_uuid,
        )

        faces_list = []
        for fr in face_rows:
            d = dict(fr)
            if isinstance(d["bbox"], str):
                d["bbox"] = json.loads(d["bbox"])
            faces_list.append(
                {
                    "face_id": d["face_id"],
                    "image_uuid": d["image_uuid"],
                    "bbox": d["bbox"],
                    "cluster_id": d["cluster_id"],
                }
            )

        return {"image": image, "faces": faces_list}

    async def delete_image_by_uuid(self, image_uuid: str) -> None:
        """
        Delete an image row (cascades to faces).

        Args:
            image_uuid: UUID of the image.
        """
        await self.string_query("DELETE FROM images WHERE uuid = $1", image_uuid)

    # Faces
    # ======================================================================

    async def insert_face(
        self,
        image_uuid: str,
        bbox: Dict[str, int],
        embedding: List[float],
        cluster_id: int = -1,
    ) -> None:
        """
        Insert a new face record for the given image UUID.

        Args:
            image_uuid: 32-character UUID of the parent image.
            bbox:       Dict with keys "x","y","width","height".
            embedding:  128-dimensional embedding vector.
            cluster_id: Cluster label (default -1).
        """
        row = await self.string_query(
            "SELECT id FROM images WHERE uuid = $1", image_uuid
        )
        if not row:
            raise ValueError(f"No image found with uuid={image_uuid}")
        image_id = row[0]["id"]

        await self.string_query(
            """
            INSERT INTO faces(image_id, image_uuid, bbox, embedding, cluster_id)
            VALUES($1, $2, $3::jsonb, $4::vector, $5)
            """,
            image_id,
            image_uuid,
            json.dumps(bbox),
            f"[{','.join(map(str, embedding))}]",
            cluster_id,
        )

    async def get_cluster_info(self, sample_size: int = 5) -> List[Dict[str, Any]]:
        """
        Return one summary row per cluster, each with up to `sample_size`
        randomly chosen faces for that cluster.

        Args:
            sample_size: maximum number of random samples per cluster.

        Returns:
            List of dicts, each:
              {
                "cluster_id": int,
                "face_count": int,
                "samples": [
                  {
                    "face_id": int,
                    "sample_blob_url": str,
                    "sample_bbox": dict
                  }, …
                ]
              }
        """
        sql = """
        WITH summary AS (
          SELECT 
            cluster_id,
            COUNT(*)     AS face_count
          FROM faces
          GROUP BY cluster_id
        )
        SELECT
          s.cluster_id,
          s.face_count,
          subs.sample_face_id   AS face_id,
          subs.sample_blob_url,
          subs.sample_bbox
        FROM summary s
        CROSS JOIN LATERAL (
          SELECT
            f.id              AS sample_face_id,
            i.azure_blob_url  AS sample_blob_url,
            f.bbox            AS sample_bbox
          FROM faces f
          JOIN images i ON i.uuid = f.image_uuid
          WHERE f.cluster_id = s.cluster_id
          ORDER BY RANDOM()
          LIMIT $1
        ) AS subs
        ORDER BY s.cluster_id
        """
        rows = await self.string_query(sql, sample_size)

        clusters: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            cid = r["cluster_id"]
            # initialize cluster dict on first sight
            if cid not in clusters:
                clusters[cid] = {
                    "cluster_id": cid,
                    "face_count": r["face_count"],
                    "samples": [],
                }
            # parse bbox if needed
            bbox = r["sample_bbox"]
            if isinstance(bbox, str):
                bbox = json.loads(bbox)
            clusters[cid]["samples"].append(
                {
                    "face_id": r["face_id"],
                    "sample_blob_url": r["sample_blob_url"],
                    "sample_bbox": bbox,
                }
            )
        # return in ascending cluster_id order
        return [clusters[cid] for cid in sorted(clusters)]

    # async def get_faces(
    #     self,
    #     *,
    #     limit: int = 50,
    #     offset: int = 0,
    # ) -> List[Dict[str, Any]]:
    #     """
    #     Return face rows paginated, parsing bbox to dict and embedding to list.
    #     """
    #     params: List[Any] = [limit, offset]

    #     rows = await self.string_query(
    #         """
    #         SELECT
    #             f.id            AS face_id,
    #             f.image_uuid,
    #             i.azure_blob_url,
    #             f.cluster_id,
    #             f.bbox,
    #             f.embedding::text AS embedding
    #         FROM faces AS f
    #         JOIN images AS i
    #           ON i.uuid = f.image_uuid
    #         ORDER BY f.id
    #         LIMIT $1 OFFSET $2
    #         """,
    #         *params,
    #     )

    #     def _vec(txt: str) -> List[float]:
    #         return [float(x) for x in txt.strip("[]").split(",")]

    #     result: List[Dict[str, Any]] = []
    #     for r in rows:
    #         d = dict(r)
    #         if isinstance(d["bbox"], str):
    #             d["bbox"] = json.loads(d["bbox"])
    #         d["embedding"] = _vec(d.pop("embedding"))
    #         result.append(d)

    #     return result

    # async def get_face_by_uuid(
    #     self,
    #     image_uuid: int,
    # ) -> Optional[Dict[str, Any]]:
    #     """
    #     Return a single face row with parsed fields, or None.

    #     Args:
    #         image_uuid: UUID of the image.

    #     Returns:
    #         Dict with keys face_id, image_uuid, azure_blob_url,
    #         bbox (dict), embedding (list), cluster_id; or None.
    #     """
    #     rows = await self.string_query(
    #         """
    #         SELECT
    #             f.id          AS face_id,
    #             f.image_uuid,
    #             i.azure_blob_url,
    #             f.bbox,
    #             f.embedding::text AS embedding,
    #             f.cluster_id
    #         FROM faces AS f
    #         JOIN images AS i
    #           ON i.uuid = f.image_uuid
    #         WHERE f.image_uuid = $1
    #         """,
    #         image_uuid,
    #     )
    #     if not rows:
    #         return None

    #     r = dict(rows[0])
    #     if isinstance(r["bbox"], str):
    #         r["bbox"] = json.loads(r["bbox"])
    #     r["embedding"] = [float(x) for x in r["embedding"].strip("[]").split(",")]
    #     return r

    async def delete_faces_by_uuid(self, image_uuid: int) -> None:
        """
        Delete a face row by its image ID.

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
        """
        Return top_k most similar faces to a reference embedding.

        Args:
            target_embedding: 128-D reference vector.
            metric:           "cosine", "l2", or "ip".
            top_k:            Number of results.

        Returns:
            list of dicts with keys face_id, image_uuid, azure_blob_url,
            cluster_id, bbox, embedding (list), distance (float).
        """
        op = {"cosine": "<=>", "l2": "<->", "ip": "<#>"}[metric]
        vec_txt = "[" + ",".join(map(str, target_embedding)) + "]"

        sql = f"""
            SELECT
                f.id              AS face_id,
                f.image_uuid,
                i.azure_blob_url,
                f.cluster_id,
                f.bbox,
                f.embedding::text AS embedding,
                f.embedding {op} '{vec_txt}'::vector AS distance
            FROM faces AS f
            JOIN images AS i
              ON i.uuid = f.image_uuid
            ORDER BY distance
            LIMIT $1
        """
        rows = await self.string_query(sql, top_k)

        def _parse(txt: str) -> List[float]:
            return [float(x) for x in txt.strip("[]").split(",")]

        results: List[Dict[str, Any]] = []
        for rec in rows:
            d = dict(rec)
            if isinstance(d["bbox"], str):
                d["bbox"] = json.loads(d["bbox"])
            d["embedding"] = _parse(d.pop("embedding"))
            results.append(d)
        return results

    async def get_all_embeddings(self) -> List[Dict[str, Any]]:
        """
        Return every face-row embedding as a Python list of floats.
        """
        rows = await self.string_query(
            "SELECT id AS face_id, embedding::text AS emb FROM faces ORDER BY id"
        )

        def _parse(txt: str) -> List[float]:
            return [float(x) for x in txt.strip("[]").split(",")]

        return [{"face_id": r["face_id"], "embedding": _parse(r["emb"])} for r in rows]

    async def update_cluster_ids(
        self,
        updates: Dict[int, int] | Sequence[Tuple[int, int]],
    ) -> None:
        """
        Bulk-update cluster IDs for faces after reclustering.

        Args:
            updates: Dict or list of (face_id, new_cluster_id) tuples.
        """
        pairs = updates.items() if isinstance(updates, dict) else updates
        sql = "UPDATE faces SET cluster_id = $1 WHERE id = $2"
        if not self._pool:
            raise RuntimeError("Pool not initialised; call connect() first")

        async with self._pool.acquire() as conn:
            try:
                await conn.executemany(sql, [(c, fid) for fid, c in pairs])
            except Exception as exc:
                raise RuntimeError(f"update_cluster_ids failed: {exc}") from exc
