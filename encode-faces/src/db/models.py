"""
SQLAlchemy declarative models for **images** and **faces**.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Image(Base):
    """
    Represents an image stored in Azure Blob Storage and tracked in the database.

    Attributes:
        id (int): Auto-incrementing primary key.
        uuid (str): 32-character hex string uniquely identifying the image.
        azure_blob_url (str): URL of the image in Azure Blob Storage.
        faces (int): Number of faces detected in the image.
        file_extension (str): File extension derived from the blob URL (e.g., 'jpg').
        created_at (datetime): Timestamp when the row was created (server default NOW()).
        last_modified (datetime): Timestamp when the row was last modified (server default NOW()).
        faces_rel (List[Face]): List of associated Face objects (one-to-many relationship).
    """

    __tablename__ = "images"

    id: int = Column(
        Integer, primary_key=True, doc="Auto-incrementing primary key of the image row."
    )
    uuid: str = Column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
        doc="32-character UUID for external reference.",
    )
    azure_blob_url: str = Column(
        String, nullable=False, doc="Azure Blob Storage URL where the image is stored."
    )
    faces: int = Column(
        Integer, nullable=False, default=0, doc="Number of detected faces in the image."
    )
    file_extension: str = Column(
        String,
        nullable=False,
        doc="File extension parsed from the blob URL (e.g. 'jpg').",
    )
    created_at: datetime = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        doc="Record creation timestamp, set by the database.",
    )
    last_modified: datetime = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        doc="Record last modification timestamp, set by the database.",
    )

    faces_rel = relationship(
        "Face",
        back_populates="image",
        cascade="all, delete-orphan",
        lazy="selectin",
        doc="List of Face objects associated with this image.",
    )


class Face(Base):
    """
    Represents a detected face within an image, including its bounding box and embedding.

    Attributes:
        id (int): Auto-incrementing primary key.
        image_id (int): Foreign key referencing Image.id.
        image_uuid (str): UUID of the parent Image for quick lookup.
        bbox (dict): Bounding box with keys 'x', 'y', 'width', 'height'.
        embedding (Vector): 128-dimensional face embedding vector.
        cluster_id (int): Cluster label for grouping similar faces.
        image (Image): Parent Image object (many-to-one relationship).
    """

    __tablename__ = "faces"

    id: int = Column(
        Integer, primary_key=True, doc="Auto-incrementing primary key of the face row."
    )
    image_id: int = Column(
        Integer,
        ForeignKey("images.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key linking to the parent image's numeric id.",
    )
    image_uuid: str = Column(
        String(32),
        nullable=False,
        index=True,
        doc="UUID of the parent image for external lookups.",
    )
    bbox: dict = Column(
        JSON,
        nullable=False,
        doc="Bounding box coordinates as JSON: {'x', 'y', 'width', 'height'}.",
    )
    embedding = Column(
        Vector(128),
        nullable=False,
        doc="128-dimensional pgvector embedding for the face.",
    )
    cluster_id: int = Column(
        Integer,
        nullable=False,
        default=-1,
        doc="Cluster label assigned after face clustering (default -1 = unclustered).",
    )

    image = relationship(
        "Image", back_populates="faces_rel", doc="Reference to the parent Image object."
    )
