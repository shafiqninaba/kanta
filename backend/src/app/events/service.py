import base64
from datetime import datetime
from io import BytesIO
from typing import List, Optional

import qrcode
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
    code: str,
    name: str | None,
    description: str | None,
    start_date_time: datetime | None,
    end_date_time: datetime | None,
    event_image_file: UploadFile | None,
) -> Event:
    new_event = Event(
        code=code,
        name=name,
        description=description,
        start_date_time=start_date_time,
        end_date_time=end_date_time,
    )

    # Generate a QR code for your link:
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(f"https://your.domain.com/events/{payload.event_code}")
    qr.make(fit=True)
    img = qr.make_image()
    buf = BytesIO()
    img.save(buf, format="PNG")
    new_event.qr_code_image = buf.getvalue()

    db.add(new_event)
    try:
        await db.commit()
        await db.refresh(new_event)
    except IntegrityError:
        await db.rollback()
        raise EventAlreadyExists(code)

    return new_event


# --------------------------------------------------------------------
# UPDATE EVENT
# --------------------------------------------------------------------
async def update_event(db: AsyncSession, payload: UpdateEventInput) -> Event:
    """
    Update fields of an existing Event identified by code.

    Args:
        db (AsyncSession): The async database session.
        payload (UpdateEventInput): Pydantic model containing the code of the event to update,
            plus any fields (new_event_code, name, description, start_date_time, end_date_time) to change.

    Returns:
        Event: The updated Event ORM instance.

    Raises:
        EventNotFound: If no Event with the given code is found.
        EventAlreadyExists: If trying to update to a code that already exists.
    """
    event = await get_event(db, payload.event_code)

    # Check if new_event_code already exists (if provided and different from current)
    if payload.new_event_code is not None and payload.new_event_code != event.code:
        stmt = select(Event).where(Event.code == payload.new_event_code)
        result = await db.execute(stmt)
        existing_event = result.scalar_one_or_none()
        if existing_event:
            raise EventAlreadyExists(payload.new_event_code)
        event.code = payload.new_event_code

    if payload.name is not None:
        event.name = payload.name
    if payload.description is not None:
        event.description = payload.description
    if payload.start_date_time is not None:
        event.start_date_time = payload.start_date_time
    if payload.end_date_time is not None:
        event.end_date_time = payload.end_date_time

    try:
        await db.commit()
        await db.refresh(event)
    except IntegrityError as exc:
        await db.rollback()
        raise EventAlreadyExists(payload.new_event_code or event.code) from exc

    return event


async def upsert_event_image(
    db: AsyncSession,
    code: str,
    image_file: UploadFile,
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
    event = await get_event(db, code)

    # read raw bytes
    raw = await image_file.read()
    event.event_image = raw

    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# --------------------------------------------------------------------
# DELETE EVENT
# --------------------------------------------------------------------
async def delete_event(db: AsyncSession, code: str) -> None:
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
