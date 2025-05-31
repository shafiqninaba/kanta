import json
import uuid
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Tuple

import face_recognition
import numpy as np
from azure.storage.blob import ContainerClient
from fastapi import HTTPException, UploadFile
from loguru import logger
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from ..events.service import get_event
from .models import Face, Image
from .schemas import (
    FaceSummary,
    ImageDetailResponse,
    ImageListItem,
    UploadImageResponse,
)


# --------------------------------------------------------------------
# GET IMAGES
# --------------------------------------------------------------------
async def get_images(
    db: AsyncSession,
    event_code: str,
    limit: int,
    offset: int,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    min_faces: Optional[int],
    max_faces: Optional[int],
    cluster_list_id: Optional[List[int]],
) -> List[ImageListItem]:
    """
    Retrieve a paginated list of images for a given event, with optional filtering.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        event_code (str): Event code to scope the query.
        limit (int): Maximum number of images to return.
        offset (int): Pagination offset.
        date_from (Optional[datetime]): Only include images created on or after this timestamp.
        date_to (Optional[datetime]): Only include images created on or before this timestamp.
        min_faces (Optional[int]): Only include images with at least this many faces.
        max_faces (Optional[int]): Only include images with at most this many faces.
        cluster_list_id (Optional[List[int]]): List of cluster IDs; only include images having faces in any of these clusters.

    Returns:
        List[ImageListItem]: List of summary metadata for each image.

    Raises:
        HTTPException 404: If the specified event does not exist.
    """
    from app.events.service import get_event

    event = await get_event(db, event_code)

    stmt = select(Image).where(Image.event_id == event.id)
    if date_from:
        stmt = stmt.where(Image.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Image.created_at <= date_to)
    if min_faces is not None:
        stmt = stmt.where(Image.faces >= min_faces)
    if max_faces is not None:
        stmt = stmt.where(Image.faces <= max_faces)
    if cluster_list_id:
        stmt = (
            stmt.join(Image.faces_rel)
            .where(Face.cluster_id.in_(cluster_list_id))
            .distinct()
        )

    stmt = stmt.order_by(Image.last_modified.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    images = result.scalars().all()
    return [ImageListItem.from_orm(img) for img in images]


# --------------------------------------------------------------------
# GET IMAGE DETAIL
# --------------------------------------------------------------------
async def get_image_detail(
    db: AsyncSession,
    uuid: str,
) -> ImageDetailResponse:
    """
    Fetch detailed metadata for a single image, including its associated faces.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        uuid (str): UUID of the image to retrieve.

    Returns:
        ImageDetailResponse: Detailed metadata and face summaries.

    Raises:
        HTTPException 404: If no image with the given UUID is found.
    """
    stmt = (
        select(Image).where(Image.uuid == uuid).options(selectinload(Image.faces_rel))
    )
    result = await db.execute(stmt)
    image = result.scalar_one_or_none()
    if image is None:
        raise HTTPException(404, f"Image `{uuid}` not found")

    faces = [
        FaceSummary(face_id=f.id, cluster_id=f.cluster_id, bbox=f.bbox)
        for f in image.faces_rel
    ]
    return ImageDetailResponse(image=ImageListItem.from_orm(image), faces=faces)


# --------------------------------------------------------------------
# CREATE IMAGES
# --------------------------------------------------------------------
# async def upload_image(
#     db: AsyncSession,
#     container: ContainerClient,
#     event_code: str,
#     upload_file,
# ) -> UploadImageResponse:
#     """
#     Process an image upload: detect faces, upload to Azure Blob Storage,
#     and persist both the Image and its Face records in the database.

#     Args:
#         db (AsyncSession): Async SQLAlchemy session for DB operations.
#         container (ContainerClient): Azure Blob Storage container client.
#         event_code (str): Unique code identifying the event.
#         upload_file (UploadFile): Incoming file object from FastAPI.

#     Returns:
#         UploadImageResponse: Contains the new image UUID, blob URL,
#             number of faces detected, face bounding boxes, and embeddings.

#     Raises:
#         HTTPException 400: If the file is not a valid image or face detection fails.
#         HTTPException 500: If uploading to Azure or database persistence fails.
#     """
#     # 0) validate image
#     if not upload_file.content_type.startswith("image/"):
#         raise HTTPException(400, "File must be an image")

#     # 1) load into numpy
#     raw = await upload_file.read()
#     try:
#         pil = PILImage.open(BytesIO(raw)).convert("RGB")
#         img_np = np.array(pil)
#     except Exception:
#         raise HTTPException(400, "Invalid image data")

#     # 2) detect faces & embeddings
#     try:
#         boxes = face_recognition.face_locations(img_np, model="hog")
#         embeddings = face_recognition.face_encodings(img_np, boxes)
#     except Exception as e:
#         logger.error(f"Face detection failed: {e}")
#         raise HTTPException(400, "Face detection failed")

#     # 3) get event and blob name
#     event = await get_event(db, event_code)
#     uid = uuid.uuid4().hex
#     ext = (upload_file.filename or "upload").rsplit(".", 1)[-1].lower()
#     blob_name = f"images/{uid}.{ext}"

#     # 4) upload to Azure
#     try:
#         container.upload_blob(
#             name=blob_name,
#             data=raw,
#             overwrite=True,
#             metadata={
#                 "event_code": event_code,
#                 "uuid": uid,
#                 "faces": str(len(embeddings)),
#                 "boxes": json.dumps(boxes),
#             },
#         )
#         props = container.get_blob_client(blob_name).get_blob_properties()
#     except Exception:
#         logger.exception("Failed to upload to Azure")
#         raise HTTPException(500, "Failed to upload to Azure")

#     # 5) persist Image row
#     image = Image(
#         event_id=event.id,
#         uuid=uid,
#         azure_blob_url=container.url + "/" + blob_name,
#         file_extension=ext,
#         faces=len(embeddings),
#         created_at=props.creation_time,
#         last_modified=props.last_modified,
#     )
#     db.add(image)
#     await db.commit()
#     await db.refresh(image)

#     # 6) persist Face rows
#     face_objs: List[Face] = []
#     for box, emb in zip(boxes, embeddings):
#         bbox = {
#             "x": box[3],
#             "y": box[0],
#             "width": box[1] - box[3],
#             "height": box[2] - box[0],
#         }
#         face = Face(
#             event_id=event.id,
#             image_id=image.id,
#             bbox=bbox,
#             embedding=emb.tolist(),
#             cluster_id=-2,
#         )
#         face_objs.append(face)
#         db.add(face)

#     await db.commit()

#     return UploadImageResponse(
#         uuid=uid,
#         blob_url=image.azure_blob_url,
#         faces=len(face_objs),
#         boxes=boxes,
#         embeddings=[e.tolist() for e in embeddings],
#     )


async def upload_image(
    *,
    db: AsyncSession,
    container: ContainerClient,
    event_code: str,
    upload_file: UploadFile,
) -> Tuple[Image, str]:
    """
    1) Validate & read raw bytes from UploadFile.
    2) Upload the raw image to Azure Blob under “images/{uuid}.{ext}”.
    3) Create an Image row with faces=0, commit and refresh.
    Returns (Image ORM instance, blob_name).
    Raises HTTPException(400) for invalid image, or HTTPException(500) for upload/DB errors.
    """
    # 1) Validate content‐type
    if not upload_file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    # 2) Read raw bytes and verify via PIL
    raw_bytes = await upload_file.read()
    try:
        ext = (upload_file.filename or "upload").rsplit(".", 1)[-1].lower()
        if ext not in {"jpg", "jpeg", "png", "gif", "bmp", "tiff"}:
            # You can choose to enforce specific extensions
            ext = "png"
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image data")

    # 3) Lookup Event (to ensure event exists and get event.id)
    event = await get_event(db, event_code)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event '{event_code}' not found")

    # 4) Generate UUID & blob_name
    image_uuid = uuid.uuid4().hex
    blob_name = f"images/{image_uuid}.{ext}"

    # 5) Upload to Azure Blob Storage
    try:
        container.upload_blob(
            name=blob_name,
            data=raw_bytes,
            overwrite=True,
            metadata={
                "event_code": event_code,
                "uuid": image_uuid,
                # faces=0 initially; will update later
                "faces": "0",
            },
        )
        # Retrieve properties for created_at / last_modified
        blob_client = container.get_blob_client(blob_name)
        props = blob_client.get_blob_properties()
    except Exception as exc:
        logger.exception(
            f"Failed to upload image to Azure for event '{event_code}': {exc}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to upload to Azure Blob Storage"
        )

    # 6) Insert Image row into DB (faces=0 for now)
    try:
        image_record = Image(
            event_id=event.id,
            uuid=image_uuid,
            azure_blob_url=f"{container.url}/{blob_name}",
            file_extension=ext,
            faces=0,
            created_at=props.creation_time,
            last_modified=props.last_modified,
        )
        db.add(image_record)
        await db.commit()
        await db.refresh(image_record)
    except Exception as exc:
        await db.rollback()
        logger.exception(f"Failed to persist Image row for '{blob_name}' in DB: {exc}")
        # Attempt to delete the blob to avoid orphaned files
        try:
            blob_client.delete_blob()
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail="Failed to record image in database"
        )

    # 7) Return the ORM object and blob_name (for background processing)
    return image_record, blob_name


async def process_faces(
    db: AsyncSession,
    container: ContainerClient,
    image_id: int,
    blob_name: str,
) -> None:
    """
    1) Download the blob (raw image) from Azure.
    2) Run face detection & embeddings.
    3) Update the Image.faces count in DB.
    4) Insert Face rows (one per detected face) into DB.
    All exceptions are logged; failures do not raise HTTPException since this is a background task.
    """
    # 1) Download the blob bytes
    try:
        downloader = container.download_blob(blob_name)
        raw_bytes = downloader.readall()
    except Exception as exc:
        logger.error(f"[process_faces] Failed to download blob '{blob_name}': {exc}")
        return

    # # 2) Load into numpy & run face_recognition
    # try:
    #     pil_image = PILImage.open(BytesIO(raw_bytes)).convert("RGB")
    #     img_np = np.array(pil_image)
    #     boxes = face_recognition.face_locations(img_np, model="hog")
    #     embeddings = face_recognition.face_encodings(img_np, boxes)
    # except Exception as exc:
    #     logger.error(
    #         f"[process_faces] Face detection failed for blob '{blob_name}': {exc}"
    #     )
    #     return

    # face_count = len(embeddings)

    # Instead of calling face_recognition directly, do it in a thread:
    def detect_faces_and_embeddings(data: bytes):
        pil_img = PILImage.open(BytesIO(data)).convert("RGB")
        img_np = np.array(pil_img)
        boxes = face_recognition.face_locations(img_np, model="hog")
        embeds = face_recognition.face_encodings(img_np, boxes)
        return boxes, embeds

    try:
        boxes, embeddings = await run_in_threadpool(
            detect_faces_and_embeddings, raw_bytes
        )
    except Exception as e:
        logger.error(f"[job] Face detection failed for '{image_id}': {e}")
        return

    face_count = len(embeddings)

    # 3) Update the Image row’s `faces` count
    try:
        image_obj = await db.get(Image, image_id)
        if not image_obj:
            logger.error(f"[process_faces] Image ID {image_id} not found in DB")
        else:
            image_obj.faces = face_count
            await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            f"[process_faces] Failed to update faces count for Image ID {image_id}: {exc}"
        )
        # Continue to insert Face rows anyway

    # 4) Insert Face rows (one per bounding box + embedding)
    face_objs: List[Face] = []
    for box, embedding in zip(boxes, embeddings):
        # face_recognition returns box as (top, right, bottom, left)
        bbox_dict = {
            "x": box[3],
            "y": box[0],
            "width": box[1] - box[3],
            "height": box[2] - box[0],
        }
        face = Face(
            event_id=image_obj.event_id if image_obj else None,
            image_id=image_id,
            bbox=bbox_dict,
            embedding=embedding.tolist(),
            cluster_id=-2,
        )
        face_objs.append(face)
        db.add(face)

    try:
        if face_objs:
            await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            f"[process_faces] Failed to insert Face rows for Image ID {image_id}: {exc}"
        )
        return

    logger.info(
        f"[process_faces] Completed face processing for Image ID {image_id}: {face_count} faces found"
    )


async def full_processing_job(
    db: AsyncSession,
    container: ContainerClient,
    event_code: str,
    image_uuid: str,
    raw_bytes: bytes,
    original_filename: str,
) -> None:
    """
    1) Validate event exists
    2) Determine extension, blob_name
    3) Upload raw_bytes to Azure
    4) Create (or update) Image row in DB with URL + metadata
    5) Run face detection on raw_bytes → (boxes, embeddings)
    6) Update Image.faces and insert Face rows
    """

    # Step 1: Ensure event exists (so we know event.id)
    try:
        event = await get_event(db, event_code)
        if not event:
            logger.error(f"[job] Event '{event_code}' not found. Aborting.")
            return
    except Exception as e:
        logger.error(f"[job] Error fetching event '{event_code}': {e}")
        return

    # Step 2: Determine extension from original filename
    ext = (
        original_filename.rsplit(".", 1)[-1].lower()
        if "." in original_filename
        else "png"
    )
    if ext not in {"jpg", "jpeg", "png", "bmp", "gif", "tiff"}:
        ext = "png"
    blob_name = f"images/{image_uuid}.{ext}"

    # Step 3: Upload raw_bytes to Azure Blob
    try:
        container.upload_blob(
            name=blob_name,
            data=raw_bytes,
            overwrite=True,
            metadata={"event_code": event_code, "uuid": image_uuid},
        )
        blob_client = container.get_blob_client(blob_name)
        props = blob_client.get_blob_properties()
        final_url = f"{container.url}/{blob_name}"
    except Exception as e:
        logger.error(f"[job] Azure upload failed for '{image_uuid}': {e}")
        return

    # Step 4: Insert or update the Image row
    image_obj = None
    try:
        # If you want a “stub” row created in the router, you'd fetch it here, otherwise create anew:
        image_obj = Image(
            event_id=event.id,
            uuid=image_uuid,
            azure_blob_url=final_url,
            file_extension=ext,
            faces=0,
            created_at=props.creation_time,
            last_modified=props.last_modified,
        )
        db.add(image_obj)
        await db.commit()
        await db.refresh(image_obj)
    except Exception as e:
        await db.rollback()
        logger.error(f"[job] Failed to insert Image row ({image_uuid}): {e}")
        # Optionally, clean up the blob to avoid orphans:
        try:
            await blob_client.delete_blob()
        except Exception:
            pass
        return

    # Step 5: Load raw_bytes into numpy & run face detection
    try:
        pil_img = PILImage.open(BytesIO(raw_bytes)).convert("RGB")
        img_np = np.array(pil_img)
        boxes = face_recognition.face_locations(img_np, model="hog")
        embeddings = face_recognition.face_encodings(img_np, boxes)
    except Exception as e:
        logger.error(f"[job] Face detection failed for '{image_uuid}': {e}")
        return

    face_count = len(embeddings)

    # Step 6: Update Image.faces & insert Face rows
    try:
        image_obj.faces = face_count
        db.add(image_obj)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"[job] Could not update face count for '{image_uuid}': {e}")
        # We’ll still try to insert individual Face rows

    faces_to_add: List[Face] = []
    for (top, right, bottom, left), emb in zip(boxes, embeddings):
        bbox = {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }
        face = Face(
            event_id=image_obj.event_id,
            image_id=image_obj.id,
            bbox=bbox,
            embedding=emb.tolist(),
            cluster_id=-2,
        )
        faces_to_add.append(face)
        db.add(face)

    try:
        if faces_to_add:
            await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"[job] Could not insert Face rows for '{image_uuid}': {e}")
        return

    logger.info(f"[job] Completed processing for '{image_uuid}': {face_count} faces")


from fastapi.concurrency import run_in_threadpool
import asyncio


async def full_processing_job(
    db: AsyncSession,
    container: ContainerClient,
    event_code: str,
    image_uuid: str,
    raw_bytes: bytes,
    original_filename: str,
) -> None:
    # Step 1: Ensure event exists
    event = await get_event(db, event_code)
    if not event:
        logger.error(f"[job] Event '{event_code}' not found.")
        return

    # Step 2: Determine extension & blob_name
    ext = (
        original_filename.rsplit(".", 1)[-1].lower()
        if "." in original_filename
        else "png"
    )
    if ext not in {"jpg", "jpeg", "png", "bmp", "gif", "tiff"}:
        ext = "png"
    blob_name = f"images/{image_uuid}.{ext}"

    # Step 3: Upload raw_bytes to Azure—but the async ContainerClient.upload_blob() is already async.
    # If you were accidentally using a sync upload_blob, wrap it in run_in_threadpool:
    try:
        # Suppose `container` is an **async** ContainerClient, so this is truly non‐blocking:
        await container.upload_blob(
            name=blob_name,
            data=raw_bytes,
            overwrite=True,
            metadata={"event_code": event_code, "uuid": image_uuid},
        )
        blob_client = container.get_blob_client(blob_name)
        props = await blob_client.get_blob_properties()
        final_url = f"{container.url}/{blob_name}"
    except Exception as e:
        logger.error(f"[job] Azure upload failed for '{image_uuid}': {e}")
        return

    # Step 4: Insert or update the Image row (async DB)
    try:
        image_obj = Image(
            event_id=event.id,
            uuid=image_uuid,
            azure_blob_url=final_url,
            file_extension=ext,
            faces=0,
            created_at=props.creation_time,
            last_modified=props.last_modified,
        )
        db.add(image_obj)
        await db.commit()
        await db.refresh(image_obj)
    except Exception as e:
        await db.rollback()
        logger.error(f"[job] Failed to insert Image row ({image_uuid}): {e}")
        try:
            await blob_client.delete_blob()
        except:
            pass
        return

    # Step 5: Run face detection on raw_bytes → THIS is CPU‐heavy
    def do_face_recognition(data: bytes):
        """All CPU‐bound/​blocking code must go in here."""
        pil_img = PILImage.open(BytesIO(data)).convert("RGB")
        img_np = np.array(pil_img)
        boxes = face_recognition.face_locations(img_np, model="hog")
        embeddings = face_recognition.face_encodings(img_np, boxes)
        return boxes, embeddings

    try:
        # This line moves `do_face_recognition` into a threadpool,
        # so the event loop is free while face_recognition runs.
        boxes, embeddings = await run_in_threadpool(do_face_recognition, raw_bytes)
    except Exception as e:
        logger.error(f"[job] Face detection failed for '{image_uuid}': {e}")
        return

    face_count = len(embeddings)

    # Step 6: Update faces count & insert Face rows (async DB)
    try:
        image_obj.faces = face_count
        db.add(image_obj)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error(f"[job] Could not update face count for '{image_uuid}'")

    for (top, right, bottom, left), emb in zip(boxes, embeddings):
        bbox = {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }
        face = Face(
            event_id=image_obj.event_id,
            image_id=image_obj.id,
            bbox=bbox,
            embedding=emb.tolist(),
            cluster_id=-2,
        )
        db.add(face)

    try:
        if boxes:
            await db.commit()
    except Exception:
        await db.rollback()
        logger.error(f"[job] Could not insert Face rows for '{image_uuid}'")

    logger.info(f"[job] Completed processing for '{image_uuid}': {face_count} faces")


# --------------------------------------------------------------------
# DELETE IMAGE
# --------------------------------------------------------------------
async def delete_image(
    db: AsyncSession,
    container: ContainerClient,
    uuid: str,
) -> None:
    """
    Delete an image and all its face records from both Azure Blob Storage and the database.

    Args:
        db (AsyncSession): Async SQLAlchemy session.
        container (ContainerClient): Azure Blob Storage container client.
        uuid (str): UUID of the image to delete.

    Returns:
        None

    Raises:
        HTTPException 404: If the image with the given UUID is not found.
        HTTPException 500: If deletion from Azure Blob Storage or database fails.
    """
    # fetch image row
    stmt = select(Image).where(Image.uuid == uuid)
    result = await db.execute(stmt)
    image = result.scalar_one_or_none()
    if image is None:
        raise HTTPException(404, f"Image `{uuid}` not found")

    # delete blob
    # parse blob_name from URL
    prefix = container.url + "/"
    blob_name = image.azure_blob_url.removeprefix(prefix)
    try:
        container.delete_blob(blob_name)
    except Exception:
        logger.warning(f"Blob `{blob_name}` not found/deleted anyway")

    # delete DB row (faces cascade)
    await db.delete(image)
    await db.commit()
