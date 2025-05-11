"""
database_orm.py
===============
Async SQLAlchemy helper for **images** and **faces** tables.

This module provides a high-level ORM interface to the `images` and `faces` tables
using SQLAlchemy Core & ORM. CRUD methods mirror the raw SQL helper for easy
swap-in, and additional vector and clustering queries are included.
"""

from __future__ import annotations
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg
from sqlalchemy import cast, delete, select, text, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload, joinedload

from .models import Base, Image, Face


def _build_url(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    ssl: str | asyncpg.SSLContext,
) -> str:
    """
    Build a SQLAlchemy DSN for asyncpg with optional sslmode.

    Args:
        host: Database host.
        port: Database port.
        user: Username.
        password: Password.
        database: Database name.
        ssl: SSL mode (e.g. 'require') or SSLContext.

    Returns:
        SQLAlchemy database URL string.
    """
    ssl_part = f"?ssl={ssl}" if isinstance(ssl, str) else ""
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}{ssl_part}"


class ORMDatabase:
    """
    High-level async helper wrapping SQLAlchemy Core & ORM for images and faces.

    Args:
        host: Database host.
        password: Database password.
        port: TCP port (default: 5432).
        user: Database user (default: 'admin').
        database: Database name (default: 'postgres').
        ssl: SSL mode or context (default: 'require').
        pool_size: Max connections (default: 5).
        echo: Enable SQL echo (default: False).
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
        pool_size: int = 5,
        echo: bool = False,
    ) -> None:
        dsn = _build_url(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            ssl=ssl,
        )
        self.engine = create_async_engine(dsn, echo=echo, pool_size=pool_size)
        self.Session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )

    async def init_models(self) -> None:
        """
        Create database tables according to SQLAlchemy models (idempotent).
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """
        Dispose the engine and close all connections.
        """
        await self.engine.dispose()

    # Images
    # ======================================================================
    async def insert_image(
        self,
        *,
        uuid: str,
        url: str,
        faces: int,
        created_at: datetime,
        last_modified: datetime,
    ) -> Image:
        """
        Insert a new image row and return the ORM instance.

        Args:
            uuid: 32-char UUID string.
            url: Azure blob URL.
            faces: Number of detected faces.
            created_at: Creation timestamp.
            last_modified: Last modified timestamp.

        Returns:
            The newly created Image.
        """
        async with self.Session() as ses:
            img = Image(
                uuid=uuid,
                azure_blob_url=url,
                faces=faces,
                created_at=created_at,
                last_modified=last_modified,
            )
            ses.add(img)
            await ses.commit()
            await ses.refresh(img)
            return img

    async def get_images(
        self,
        *,
        min_faces: Optional[int] = None,
        max_faces: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Image]:
        """
        Retrieve images with optional face-count filters and pagination.

        Args:
            min_faces: Minimum face count.
            max_faces: Maximum face count.
            limit: Max rows to return.
            offset: Rows to skip.

        Returns:
            List of Image ORM instances (faces relation eagerly loaded).
        """
        stmt = select(Image).options(selectinload(Image.faces_rel))
        if min_faces is not None:
            stmt = stmt.where(Image.faces >= min_faces)
        if max_faces is not None:
            stmt = stmt.where(Image.faces <= max_faces)
        stmt = stmt.order_by(Image.created_at.desc()).limit(limit).offset(offset)

        async with self.Session() as ses:
            res = await ses.execute(stmt)
            return list(res.unique().scalars().all())

    async def get_image_by_uuid(self, uuid: str) -> Optional[Image]:
        """
        Fetch a single image by UUID (includes faces). Returns None if missing.
        """
        stmt = (
            select(Image)
            .options(selectinload(Image.faces_rel))
            .where(Image.uuid == uuid)
            .limit(1)
        )
        async with self.Session() as ses:
            return await ses.scalar(stmt)

    async def delete_image(self, uuid: str) -> None:
        """
        Delete an image and its faces (CASCADE).

        Args:
            uuid: UUID of the image to delete.
        """
        async with self.Session() as ses:
            await ses.execute(delete(Image).where(Image.uuid == uuid))
            await ses.commit()

    # Faces
    # ======================================================================
    async def insert_face(
        self,
        *,
        image_uuid: str,
        cluster_id: int,
        bbox: Dict[str, int],
        embedding: Sequence[float],
    ) -> Face:
        """
        Insert a face linked to an image by UUID.

        Args:
            image_uuid: Parent image UUID.
            cluster_id: Cluster label.
            bbox: Dict with keys x,y,width,height.
            embedding: 128-float list.

        Returns:
            The newly created Face.
        """
        async with self.Session() as ses:
            img = await ses.scalar(select(Image).where(Image.uuid == image_uuid))
            if img is None:
                raise ValueError(f"No image with uuid={image_uuid}")
            face = Face(
                image_id=img.id,
                image_uuid=image_uuid,
                cluster_id=cluster_id,
                bbox=bbox,
                embedding=list(embedding),
            )
            ses.add(face)
            await ses.commit()
            await ses.refresh(face)
            return face

    async def get_cluster_info(self, sample_size: int = 5) -> List[Dict[str, Any]]:
        """
        Return one summary per cluster, with up to `sample_size` random face samples.
        Uses a raw SQL LATERAL subquery under the hood.
        """
        sql = text("""
        WITH summary AS (
          SELECT
            cluster_id,
            COUNT(*) AS face_count
          FROM faces
          GROUP BY cluster_id
        )
        SELECT
          s.cluster_id,
          s.face_count,
          subs.sample_face_id AS face_id,
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
          LIMIT :k
        ) subs
        ORDER BY s.cluster_id
        """)
        async with self.engine.connect() as conn:
            res = await conn.execute(sql, {"k": sample_size})
            rows = res.mappings().all()

        clusters: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            cid = r["cluster_id"]
            if cid not in clusters:
                clusters[cid] = {
                    "cluster_id": cid,
                    "face_count": r["face_count"],
                    "samples": [],
                }
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
        return [clusters[cid] for cid in sorted(clusters)]

    # async def get_faces_by_cluster(
    #     self,
    # ) -> Dict[int, List[Dict[str, Any]]]:
    #     """
    #     Return faces grouped by cluster_id.

    #     Returns:
    #         Dict mapping cluster_id to list of face dicts with keys:
    #         face_id, image_uuid, azure_blob_url, bbox, embedding.
    #     """
    #     sql = text(
    #         """
    #         SELECT
    #           f.id            AS face_id,
    #           f.cluster_id,
    #           f.image_uuid,
    #           i.azure_blob_url,
    #           f.bbox,
    #           CAST(f.embedding AS text) AS embedding
    #         FROM faces f
    #         JOIN images i ON i.uuid = f.image_uuid
    #         ORDER BY f.cluster_id, f.id
    #         """
    #     )
    #     async with self.engine.connect() as conn:
    #         res = await conn.execute(sql)
    #         rows = res.mappings().all()

    #     def _vec(txt: str) -> List[float]:
    #         return [float(x) for x in txt.strip("[]").split(",")]  # noqa: E501

    #     clusters: Dict[int, List[Dict[str, Any]]] = {}
    #     for r in rows:
    #         d = dict(r)
    #         if isinstance(d["bbox"], str):
    #             d["bbox"] = json.loads(d["bbox"])
    #         d["embedding"] = _vec(d.pop("embedding"))
    #         clusters.setdefault(d["cluster_id"], []).append(d)
    #     return clusters

    # async def get_faces(
    #     self,
    #     *,
    #     image_uuid: Optional[str] = None,
    #     limit: int = 50,
    #     offset: int = 0,
    # ) -> List[Face]:
    #     """
    #     Fetch faces, optionally filtered by image UUID, with pagination.
    #     """
    #     stmt = select(Face).order_by(Face.id).limit(limit).offset(offset)
    #     if image_uuid:
    #         stmt = stmt.where(Face.image_uuid == image_uuid)

    #     async with self.Session() as ses:
    #         return list((await ses.scalars(stmt)).all())

    async def delete_faces_by_uuid(self, image_uuid: str) -> None:
        """
        Delete all faces associated with a given image UUID.
        """
        async with self.Session() as ses:
            await ses.execute(delete(Face).where(Face.image_uuid == image_uuid))
            await ses.commit()

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
        Return top_k most similar faces by vector distance.

        Args:
            target_embedding: 128-D list.
            metric: 'cosine', 'l2', or 'ip'.
            top_k: Number of results.

        Returns:
            List of dicts with keys: face_id, image_uuid,
                azure_blob_url, cluster_id, bbox, embedding, distance.
        """
        op = {"cosine": "<=>", "l2": "<->", "ip": "<#>"}[metric]
        vec_txt = "[" + ",".join(map(str, target_embedding)) + "]"
        sql = text(
            f"""
            SELECT
              f.id            AS face_id,
              f.image_uuid,
              i.azure_blob_url,
              f.cluster_id,
              f.bbox,
              CAST(f.embedding AS text) AS embedding,
              f.embedding {op} '{vec_txt}'::vector AS distance
            FROM faces f
            JOIN images i ON i.uuid = f.image_uuid
            ORDER BY distance
            LIMIT :k
            """
        )
        async with self.engine.connect() as conn:
            res = await conn.execute(sql, {"k": top_k})
            rows = res.mappings().all()

        def _parse(txt: str) -> List[float]:
            return [float(x) for x in txt.strip("[]").split(",")]

        return [{**dict(r), "embedding": _parse(r["embedding"])} for r in rows]

    async def get_all_embeddings(self) -> List[Dict[str, Any]]:
        """
        Fetch every embedding as a Python list of floats.
        """
        stmt = select(
            Face.id.label("face_id"),
            cast(Face.embedding, String).label("emb"),
        ).order_by(Face.id)
        async with self.Session() as ses:
            res = await ses.execute(stmt)
            rows = res.mappings().all()

        def _parse(txt: str) -> List[float]:
            return [float(x) for x in txt.strip("[]").split(",")]

        return [{"face_id": r["face_id"], "embedding": _parse(r["emb"])} for r in rows]

    async def update_cluster_ids(
        self, updates: Dict[int, int] | Sequence[Tuple[int, int]]
    ) -> None:
        """
        Bulk-update cluster_id for multiple faces.

        Args:
            updates: Mapping face_id -> new_cluster_id or sequence of tuples.
        """
        pairs = updates.items() if isinstance(updates, dict) else updates
        async with self.Session() as ses:
            for face_id, new_cluster in pairs:
                await ses.execute(
                    text("UPDATE faces SET cluster_id = :c WHERE id = :id"),
                    {"c": new_cluster, "id": face_id},
                )
            await ses.commit()

    async def string_query(
        self, sql: str, params: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """
        Execute raw SQL and return list-of-dicts.

        Args:
            sql: SQL statement with named parameters.
            params: Dict of parameter values.

        Returns:
            List of row dicts.
        """
        async with self.engine.connect() as conn:
            res = await conn.execute(text(sql), params or {})
            return [dict(r) for r in res.mappings().all()]
