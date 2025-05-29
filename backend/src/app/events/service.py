import os
from io import BytesIO
from typing import List, Optional

import qrcode
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContainerClient
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import EventAlreadyExists, EventNotFound
from .models import Event
from .schemas import CreateEventInput, UpdateEventInput


# --------------------------------------------------------------------
# GET EVENTS
# --------------------------------------------------------------------
async def get_events(
    db: AsyncSession,
    event_code: Optional[str] = None,
    running: Optional[bool] = None,
) -> List[Event]:
    """
    Fetch one or more Event records, optionally filtering by code and running status.

    Args:
        db (AsyncSession): The async database session.
        code (Optional[str]): If provided, only return the Event with this code.
        running (Optional[bool]): If True, return only events where now() is between start and end;
            if False, only events outside that range; if None, return regardless of running status.

    Returns:
        List[Event]: A list of Event ORM instances matching the filters.
    """
    stmt = select(Event)
    if event_code:
        stmt = stmt.where(Event.code == event_code)

    result = await db.execute(stmt)
    events = result.scalars().all()

    # In-memory filter on @property running
    if running is not None:
        events = [e for e in events if e.running == running]
    return events


async def get_event(db: AsyncSession, code: str) -> Event:
    """
    Retrieve a single Event by its unique code.

    Args:
        db (AsyncSession): The async database session.
        code (str): The unique event code to look up.

    Returns:
        Event: The matching Event ORM instance.

    Raises:
        EventNotFound: If no Event with the given code is found.
    """
    result = await db.execute(select(Event).where(Event.code == code))
    event = result.scalar_one_or_none()
    if event is None:
        raise EventNotFound(code)
    return event


# --------------------------------------------------------------------
# CREATE EVENT
# --------------------------------------------------------------------
async def create_event(
    db: AsyncSession,
    payload: CreateEventInput,
    blob_service: BlobServiceClient,
) -> Event:
    """
    Create a new Event record in the database.

    Args:
        db (AsyncSession): The async database session.
        payload (CreateEventInput): Pydantic model containing the event code, name,
            description, start_date_time, and end_date_time.

    Returns:
        Event: The newly created Event ORM instance, with all fields populated (including id and created_at).

    Raises:
        EventAlreadyExists: If an Event with the same code already exists (unique constraint violation).
    """
    # 1) Create the Event ORM
    new_event = Event(
        code=code,
        name=name,
        description=description,
        start_date_time=start_date_time,
        end_date_time=end_date_time,
    )

    # 2) Generate QR image into memory
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(f"https://your.domain.com/events/{payload.event_code}")
    qr.make(fit=True)
    img = qr.make_image()
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    qr_bytes = buf.getvalue()

    # 3) Grab/create the container
    container = blob_service.get_container_client(payload.event_code)
    try:
        container.create_container(public_access="blob")
    except ResourceExistsError:
        pass

    # 4) Upload the QR under `assets/qr.png`
    asset_path = "assets/qr.png"
    container.upload_blob(
        name=asset_path,
        data=qr_bytes,
        overwrite=True,
        metadata={"event_code": payload.event_code},
    )
    # (Optional) store the public URL back on the model
    new_event.qr_code_image_url = f"{container.url}/{asset_path}"

    # 5) Persist the Event row
    db.add(new_event)
    try:
        await db.commit()
        await db.refresh(new_event)
    except IntegrityError as exc:
        await db.rollback()
        raise EventAlreadyExists(payload.event_code) from exc

    return new_event


# --------------------------------------------------------------------
# UPDATE EVENT
# --------------------------------------------------------------------
async def update_event(
    db: AsyncSession,
    payload: UpdateEventInput,
    blob_service: BlobServiceClient,
) -> Event:
    """
    Update an existing Event record with new data.

    Args:
        db (AsyncSession): The async database session.
        payload (UpdateEventInput): Pydantic model containing the event code, new code, name,
            description, start_date_time, and end_date_time.
        blob_service (BlobServiceClient): Azure Blob Service client for managing event containers.

    Returns:
        Event: The updated Event ORM instance with all fields populated (including id and created_at).

    Raises:
        EventNotFound: If no Event with the given code is found.
        EventAlreadyExists: If renaming the event results in a code that already exists.
    """
    # 1) Fetch or 404
    event = await get_event(db, payload.event_code)
    old_code = event.code

    # 2) If renaming, check uniqueness in DB
    if payload.new_event_code and payload.new_event_code != old_code:
        stmt = select(Event).where(Event.code == payload.new_event_code)
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise EventAlreadyExists(payload.new_event_code)
        event.code = payload.new_event_code

    # 3) Apply other fields
    for field in ("name", "description", "start_date_time", "end_date_time"):
        val = getattr(payload, field)
        if val is not None:
            setattr(event, field, val)

    # 4) Commit DB
    try:
        await db.commit()
        await db.refresh(event)
    except IntegrityError as exc:
        await db.rollback()
        raise EventAlreadyExists(payload.new_event_code or old_code) from exc

    # 5) Rename container in Azure if code changed
    if payload.new_event_code and payload.new_event_code != old_code:
        old_container = old_code.lower()
        new_container = payload.new_event_code.lower()

        # 5a) Create the new container
        try:
            blob_service.create_container(new_container, public_access="blob")
        except ResourceExistsError:
            pass

        # 5b) Copy each blob from old → new
        old_client = blob_service.get_container_client(old_container)
        new_client = blob_service.get_container_client(new_container)
        for blob in old_client.list_blobs():
            src = old_client.get_blob_client(blob.name)
            dest = new_client.get_blob_client(blob.name)
            # start copy; URL is source blob URL with SAS or public if anonymous
            dest.start_copy_from_url(src.url)

        # 5c) Delete the old container
        try:
            blob_service.delete_container(old_container)
        except ResourceNotFoundError:
            pass

    # RIP: just realised that database images azure blob URL is NOT HANDLED...same for faces
    # In practice, this means that if you change the event code,
    # the image URLs will not automatically update.
    # FOR NOW, WE LET THE EVENT CODE BE PERMANENT.

    return event


async def upsert_event_image(
    db: AsyncSession,
    code: str,
    image_file: UploadFile,
    container: ContainerClient,
):
    """
    Read bytes from image_file, attach them to event.event_image,
    commit & refresh. Raises EventNotFound if code not found.

    Args:
        db (AsyncSession): The async database session.
        code (str): The unique event code to update.
        image_file (UploadFile): The image file to attach or replace.

    Returns:
        Event: The updated Event ORM instance with the new image attached.
    """
    # 1) fetch or 404
    event = await get_event(db, code)

    # 2) read bytes & determine extension
    raw = await image_file.read()
    ext = os.path.splitext(image_file.filename or "")[1].lstrip(".").lower() or "jpg"
    blob_path = f"assets/event_image.{ext}"

    # 3) upload to Azure
    container.upload_blob(
        name=blob_path,
        data=raw,
        overwrite=True,
        metadata={"event_code": code},
    )
    # compute the public URL
    image_url = f"{container.url}/{blob_path}"

    # 4) persist the URL (or bytes if you still want)
    event.event_image_url = (
        image_url  # make sure `event_image_url` exists on your model
    )
    # if you still have a binary column you can skip or also set `event.event_image = raw`

    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# --------------------------------------------------------------------
# DELETE EVENT
# --------------------------------------------------------------------
async def delete_event(
    db: AsyncSession,
    code: str,
    blob_service: BlobServiceClient,
) -> None:
    """
    Delete an existing Event (and cascade to images and faces via ORM relationships).

    Args:
        db (AsyncSession): The async database session.
        code (str): The unique event code to delete.

    Raises:
        EventNotFound: If no Event with the given code is found.
    """
    event = await get_event(db, code)
    await db.delete(event)
    await db.commit()

    container_name = code.lower()
    try:
        blob_service.delete_container(container_name)
    except ResourceNotFoundError:
        # if the container did not exist, ignore
        pass
