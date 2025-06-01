import io
import re
from datetime import date, datetime
from datetime import time as t

import requests
import streamlit as st
from utils.api import (
    create_event,
    get_events,
    update_event,
    upload_event_image,
)
from utils.session import get_event_selection, init_session_state

# Page Configuration
st.set_page_config(page_title="Events Manager", page_icon="🎭", layout="centered")

# Constants
AZURE_CONTAINER_NAME_REGEX = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{1,61}[a-z0-9])?$")
MIN_LEN = 3
MAX_LEN = 63


def main() -> None:
    # Session State Initialization
    init_session_state()
    get_event_selection()
    ss = st.session_state
    ss.setdefault("edit_mode", False)
    ss.setdefault("just_created", False)

    # --------------------------------------------------------------------
    # Header
    # --------------------------------------------------------------------
    st.title("Events")
    st.markdown("Manage your events and maintain a collaborative photo album.")

    tab_current, tab_create = st.tabs(["Current Event", "Create New Event"])

    # --------------------------------------------------------------------
    # Current Event Tab
    # --------------------------------------------------------------------
    with tab_current:
        if not ss.get("event_code"):
            st.warning(
                "Select or create an event first to view or edit existing events."
            )
        else:
            code = ss.event_code
            event = get_events(event_code=ss.event_code)[0]

            # Get image and QR code URLs
            image_url = event.get("event_image_url") or None
            qr_url = event.get("qr_code_image_url") or None

            # Build columns for event image and QR code
            col1, col2 = st.columns([3, 2], gap="medium")

            # --------------------------------------------------------------------
            # Column 1: Event Image and Upload Form
            # --------------------------------------------------------------------
            with col1:
                st.subheader(event.get("name") or code)
                img_data = None
                if image_url:
                    try:
                        resp = requests.get(image_url)
                        resp.raise_for_status()
                        img_data = resp.content
                    except Exception:
                        pass
                # Display event image or blank if none
                if img_data:
                    st.image(
                        img_data,
                        caption=event.get("description") or "No description provided.",
                        use_container_width=True,
                    )
                else:
                    st.empty()

                # Image upload form
                with st.expander("Change Event Image"):
                    with st.form("upload_image_form", clear_on_submit=True):
                        uploaded = st.file_uploader(
                            "Select new event image", type=["jpg", "jpeg", "png"]
                        )
                        if st.form_submit_button("Upload"):
                            if not uploaded:
                                st.warning("Please select a file first.")
                            else:
                                buf = io.BytesIO(uploaded.getvalue())
                                buf.name = uploaded.name
                                try:
                                    upload_event_image(event_code=code, image_file=buf)
                                    st.success("Event image updated!")
                                    st.rerun()
                                except requests.HTTPError as err:
                                    detail = err.response.text or str(err)
                                    st.error(
                                        f"Upload failed ({err.response.status_code}): {detail}"
                                    )
                                except Exception as e:
                                    st.error(f"Unexpected error: {e}")

            # --------------------------------------------------------------------
            # Column 2: Event QR Code
            # --------------------------------------------------------------------
            with col2:
                st.subheader("Event QR Code")
                if qr_url:
                    qr_data = None
                    try:
                        qr_resp = requests.get(qr_url)
                        qr_resp.raise_for_status()
                        qr_data = qr_resp.content
                    except Exception:
                        pass
                    if qr_data:
                        st.image(
                            qr_data,
                            width=300,
                            caption="Scan this QR code to join the event",
                        )
                        st.download_button(
                            "Download QR Code",
                            data=qr_data,
                            file_name=f"{code}_qr.png",
                            mime="image/png",
                        )
                    else:
                        st.empty()

            # --------------------------------------------------------------------
            # Event Details and Edit Form
            # --------------------------------------------------------------------
            st.divider()
            st.subheader("Event Details")
            st.markdown("Here you can view and edit the event details.")

            with st.form("event_form", clear_on_submit=False):
                name = st.text_input(
                    "Name",
                    value=event.get("name") or "",
                    disabled=not ss.edit_mode,
                    help="Name of your event.",
                )
                desc = st.text_area(
                    "Description",
                    value=event.get("description") or "",
                    disabled=not ss.edit_mode,
                    help="Description of your event.",
                )
                c1, c2 = st.columns(2)
                start_date = c1.date_input(
                    "Start Date",
                    value=date.fromisoformat(event["start_date_time"][:10]),
                    disabled=not ss.edit_mode,
                    help="Start date of your event.",
                )
                start_time = c2.time_input(
                    "Start Time",
                    value=datetime.fromisoformat(event["start_date_time"]).time(),
                    disabled=not ss.edit_mode,
                    help="Start time of your event.",
                )
                c3, c4 = st.columns(2)
                end_date = c3.date_input(
                    "End Date",
                    value=date.fromisoformat(event["end_date_time"][:10]),
                    disabled=not ss.edit_mode,
                    help="End date of your event.",
                )
                end_time = c4.time_input(
                    "End Time",
                    value=datetime.fromisoformat(event["end_date_time"]).time(),
                    disabled=not ss.edit_mode,
                    help="End time of your event.",
                )
                # Editing mode
                if ss.edit_mode:
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("Save Changes"):
                        try:
                            update_event(
                                event_code=code,
                                name=name or None,
                                description=desc or None,
                                start_date_time=datetime.combine(
                                    start_date, start_time
                                ),
                                end_date_time=datetime.combine(end_date, end_time),
                            )
                            st.success("Event updated!")
                            ss.edit_mode = False
                            st.rerun()
                        except requests.HTTPError as err:
                            detail = err.response.text or str(err)
                            st.error(
                                f"Update failed ({err.response.status_code}): {detail}"
                            )
                        except Exception as e:
                            st.error(f"Unexpected error: {e}")
                    if b2.form_submit_button("Cancel"):
                        ss.edit_mode = False
                        st.rerun()
                else:
                    if st.form_submit_button("Edit Event"):
                        ss.edit_mode = True
                        st.rerun()

    # --------------------------------------------------------------------
    # Create New Event Tab
    # --------------------------------------------------------------------
    with tab_create:
        st.subheader("Create New Event")
        with st.form("create_form"):
            code = st.text_input(
                "Event Code",
                placeholder="myevent123",
                help="Unique identifier for your event. "
                "Must only consist of lowercase letters, numbers, and between 3 and 63 characters long.",
                max_chars=MAX_LEN,
            ).strip()
            name = st.text_input(
                "Event Name", placeholder="My Awesome Event", help="Name of your event."
            )
            desc = st.text_area(
                "Description",
                placeholder="A fun event for everyone",
                help="Description of your event.",
            )
            c1, c2 = st.columns(2)
            d0 = c1.date_input(
                "Start Date",
                value=date.today(),
                help="Start date of your event.",
            )
            t0 = c2.time_input(
                "Start Time",
                value=t(9, 0),
                step=1800,
                help="Start time of your event.",
            )
            c3, c4 = st.columns(2)
            d1 = c3.date_input(
                "End Date",
                value=date.today(),
                help="End date of your event.",
            )
            t1 = c4.time_input(
                "End Time",
                value=t(17, 0),
                step=1800,
                help="End time of your event.",
            )

            if st.form_submit_button("Create Event"):
                # Validation Checks, Ren Hwa: in the future, can use pydantic models for validation
                if not code:
                    st.toast("Event Code is required.", icon="🚨")
                if len(code) < MIN_LEN or len(code) > MAX_LEN:
                    st.toast(
                        f"Event Code must be between {MIN_LEN} and {MAX_LEN} characters.",
                        icon="🚨",
                    )
                if not AZURE_CONTAINER_NAME_REGEX.match(code):
                    st.toast(
                        "Invalid Event Code. "
                        "Must consist of lowercase letters, numbers, and single hyphens, "
                        "cannot begin or end with a hyphen, and cannot have consecutive hyphens.",
                        icon="🚨",
                    )
                if not name:
                    st.toast("Event Name is required.", icon="🚨")
                else:
                    try:
                        new_event = create_event(
                            event_code=code.strip(),
                            name=name or None,
                            description=desc or None,
                            start_date_time=datetime.combine(d0, t0),
                            end_date_time=datetime.combine(d1, t1),
                        )
                        ss.event_code = new_event["code"]
                        ss.just_created = True
                        st.rerun()

                    except requests.HTTPError as err:
                        detail = err.response.text or str(err)
                        st.error(
                            f"Creation failed ({err.response.status_code}): {detail}"
                        )

                    except Exception as e:
                        st.error(f"Unexpected error: {e}")

        if ss.just_created:
            # fetch the newly created event details
            new_event = get_events(event_code=code)[0]

            # congratulatory message
            st.balloons()
            st.success(
                f"Event **{new_event.get('name', code)}** created successfully! 🎉"
            )

            # Display newly created event QR code if available
            qr_url = new_event.get("qr_code_image_url")
            if qr_url:
                st.subheader("Event QR Code")
                st.divider(divider="violet")

                qr_data = None
                try:
                    qr_resp = requests.get(qr_url)
                    qr_resp.raise_for_status()
                    qr_data = qr_resp.content
                except Exception:
                    pass

                if qr_data:
                    st.image(
                        qr_data,
                        width=300,
                        caption="Scan this QR code to join the event",
                    )
                    st.download_button(
                        "Download Event QR Code",
                        data=qr_data,
                        file_name=f"{ss.event_code}_qr.png",
                        mime="image/png",
                    )
                else:
                    st.empty()

            # Reset just_created flag
            ss.just_created = False


if __name__ == "__main__":
    main()
