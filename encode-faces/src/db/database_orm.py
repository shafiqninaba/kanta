"""
database_orm.py
===============
Async SQLAlchemy helper for **images** and **faces**.

The constructor now mirrors the raw‑SQL helper so you can initialise with
keyword parameters instead of a single DATABASE_URL string.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg
from sqlalchemy import cast, String
from sqlalchemy import delete, text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload, selectinload

from .models import Base, Face, Image


def _build_url(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    ssl: str | asyncpg.SSLContext,
) -> str:
    """Return an SQLAlchemy DSN for asyncpg with optional sslmode."""
    # asyncpg treats "require" as a flag string; SQLAlchemy passes it verbatim
    ssl_part = f"?ssl={ssl}" if isinstance(ssl, str) else ""
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}{ssl_part}"


class ORMDatabase:
    """High‑level async helper wrapping SQLAlchemy Core & ORM.

    Args:
        host: Database hostname or IP.
        password: User password.
        port: TCP port (default: 5432).
        user: Database user (default: ``admin``).
        database: Database name (default: ``postgres``).
        ssl: SSL mode string (``require``/``disable``/etc.) or ``asyncpg.SSLContext``.
        pool_size: Maximum pooled connections (default: 5).
        echo: Enable SQL echo for debugging.
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
            bind=self.engine, expire_on_commit=False
        )

    # schema management
    async def init_models(self) -> None:
        """Create tables if they do not exist (idempotent)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose the engine (close connection pool)."""
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
        """Insert and return an :class:`Image` row."""
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

    async def delete_image(self, uuid: str) -> None:
        """Delete an image and all its faces (CASCADE)."""
        async with self.Session() as ses:
            await ses.execute(delete(Image).where(Image.uuid == uuid))
            await ses.commit()

    async def get_images(
        self,
        *,
        min_faces: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Image]:
        """Return images with their faces eagerly loaded."""
        stmt = select(Image).options(selectinload(Image.faces_rel))
        if min_faces is not None:
            stmt = stmt.where(Image.faces >= min_faces)
        stmt = stmt.order_by(Image.created_at.desc()).limit(limit).offset(offset)

        async with self.Session() as ses:
            result = await ses.execute(stmt)
            # selectinload doesn't duplicate, but `.unique()` is future‑proof
            return list(result.unique().scalars().all())

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
        """Insert a face linked by ``image_uuid``."""
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

    async def get_faces(
        self,
        *,
        image_uuid: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Face]:
        stmt = select(Face).order_by(Face.id).limit(limit).offset(offset)
        if image_uuid:
            stmt = stmt.where(Face.image_uuid == image_uuid)

        async with self.Session() as ses:
            return list(await ses.scalars(stmt))

    async def delete_faces_for_image(self, image_uuid: str) -> None:
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
                CAST(f.embedding AS text) AS embedding,
                f.embedding {op} '{vec_txt}'::vector AS distance
            FROM faces AS f
            JOIN images AS i ON i.uuid = f.image_uuid
            ORDER BY distance
            LIMIT :k
            """

        async with self.engine.connect() as conn:
            res = await conn.execute(text(sql), {"k": top_k})
            rows = res.mappings().all()

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
        """Return every embedding row, parsed to List[float]."""
        stmt = select(
            Face.id.label("face_id"), cast(Face.embedding, String).label("emb")
        ).order_by(Face.id)

        async with self.Session() as ses:
            result = await ses.execute(stmt)

            def _parse(txt: str) -> List[float]:
                return [float(x) for x in txt.strip("[]").split(",")]

            return [
                {"face_id": r["face_id"], "embedding": _parse(r["emb"])}
                for r in result.mappings().all()
            ]

    async def update_cluster_ids(
        self, updates: Dict[int, int] | Sequence[Tuple[int, int]]
    ) -> None:
        """Bulk update *cluster_id* for multiple face rows."""
        pairs = updates.items() if isinstance(updates, dict) else updates
        async with self.Session() as ses:
            for face_id, new_cluster in pairs:
                await ses.execute(
                    text("UPDATE faces SET cluster_id = :c WHERE id = :id"),
                    {"c": new_cluster, "id": face_id},
                )
            await ses.commit()

    async def raw_query(
        self, sql: str, params: Dict[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        """Execute raw SQL and return list‑of‑dict rows."""
        async with self.engine.connect() as conn:
            res = await conn.execute(text(sql), params or {})
            return [dict(r) for r in res.mappings().all()]
