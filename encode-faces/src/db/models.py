"""
SQLAlchemy declarative models for **images** and **faces**.

Requires:
    pip install sqlalchemy[asyncio] pgvector psycopg[binary]
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Image(Base):
    """Images table (see migrations for trigger that fills `file_extension`)."""

    __tablename__ = "images"

    id: int = Column(Integer, primary_key=True)
    uuid: str = Column(String(32), unique=True, nullable=False, index=True)
    azure_blob_url: str = Column(String, nullable=False)
    file_extension: str = Column(String, nullable=False)
    faces: int = Column(Integer, nullable=False, default=0)
    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    last_modified: datetime = Column(
        DateTime, nullable=False, server_default=func.now()
    )

    faces_rel = relationship(
        "Face",
        back_populates="image",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Face(Base):
    """Faces table holding bbox + 128‑D embedding."""

    __tablename__ = "faces"

    id: int = Column(Integer, primary_key=True)
    image_id: int = Column(
        Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_uuid: str = Column(String(32), nullable=False, index=True)
    cluster_id: int = Column(Integer, nullable=False, default=0)
    bbox: dict = Column(JSON, nullable=False)
    embedding = Column(Vector(128), nullable=False)

    image = relationship("Image", back_populates="faces_rel")
