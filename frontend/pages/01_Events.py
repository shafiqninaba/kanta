import io
import time
from datetime import date, datetime, time as t

import requests
import streamlit as st

from utils.api import (
    create_event,
    get_events,
    update_event,
    upload_event_image,
)
from utils.session import get_event_selection, init_session_state


# ────────────────────────── Helpers ──────────────────────────
def get_current_event(code: str) -> dict | None:
    """Always fetch fresh data to avoid client-side caching."""
    try:
        return get_events(event_code=code)[0]
    except Exception as err:
        st.error(f"Could not load event: {err}")
        return None


def cache_bust(url: str | None) -> str | None:
    """Append a throw-away timestamp so the browser won’t reuse a stale image."""
    if not url:
        return None
    return f"{url}?ts={int(time.time())}"


# ────────────────────────── Main UI ──────────────────────────
def main() -> None:
    st.set_page_config(page_title="Events Manager", page_icon="🎭", layout="wide")

    # session state
    init_session_state()
    get_event_selection()
    ss = st.session_state
    ss.setdefault("edit_mode", False)
    ss.setdefault("just_created", False)

    st.title("Events")
    st.markdown("Manage your events and maintain a collaborative photo album.")

    tab_current, tab_create = st.tabs(["Current Event", "Create New Event"])

    # ─── Tab 1 ──────────────────────────────────────────────────
    with tab_current:
        st.header("Current Event")

        if not ss.get("event_code"):
            st.warning("Select or create an event first.")
            return

        event = get_current_event(ss.event_code)
        if not event:
            return

        col_img, col_details = st.columns([3, 3], gap="medium")

        # ── Event image & uploader ─────────────────────────────
        with col_img:
            st.subheader("Event Image")

            img_url = cache_bust(event.get("event_image_url"))
            placeholder = "https://via.placeholder.com/300?text=No+Event+Image"

            st.image(
                img_url or placeholder,
                caption=event.get("name") or event["code"],
                use_container_width=True,
            )

            with st.form("upload_image_form", clear_on_submit=True):
                uploaded = st.file_uploader(
                    "Select new event image",
                    type=["jpg", "jpeg", "png"],
                )
                if st.form_submit_button("Upload Image"):
                    if not uploaded:
                        st.warning("Please select a file first.")
                    else:
                        try:
                            buf = io.BytesIO(uploaded.getvalue())
                            buf.name = uploaded.name
                            upload_event_image(ss.event_code, buf)
                            st.success("Image updated!")
                            st.rerun()
                        except requests.HTTPError as err:
                            st.error(f"Upload failed: {err}")

        # ── Event details form ─────────────────────────────────
        with col_details.form("event_form"):
            st.subheader("Event Details")

            name = st.text_input(
                "Name", value=event.get("name") or "", disabled=not ss.edit_mode
            )
            desc = st.text_area(
                "Description",
                value=event.get("description") or "",
                disabled=not ss.edit_mode,
            )

            c1, c2 = st.columns(2)
            start_date = c1.date_input(
                "Start Date",
                value=date.fromisoformat(event["start_date_time"][:10]),
                disabled=not ss.edit_mode,
            )
            start_time = c2.time_input(
                "Start Time",
                value=datetime.fromisoformat(event["start_date_time"]).time(),
                disabled=not ss.edit_mode,
            )
            c3, c4 = st.columns(2)
            end_date = c3.date_input(
                "End Date",
                value=date.fromisoformat(event["end_date_time"][:10]),
                disabled=not ss.edit_mode,
            )
            end_time = c4.time_input(
                "End Time",
                value=datetime.fromisoformat(event["end_date_time"]).time(),
                disabled=not ss.edit_mode,
            )

            if ss.edit_mode:
                b1, b2 = st.columns(2)
                if b1.form_submit_button("Save Changes"):
                    try:
                        update_event(
                            event_code=ss.event_code,
                            name=name or None,
                            description=desc or None,
                            start_date_time=datetime.combine(start_date, start_time),
                            end_date_time=datetime.combine(end_date, end_time),
                        )
                        st.success("Event updated!")
                        ss.edit_mode = False
                        st.rerun()
                    except requests.HTTPError as err:
                        st.error(f"Update failed: {err}")
                if b2.form_submit_button("Cancel"):
                    ss.edit_mode = False
                    st.rerun()
            else:
                if st.form_submit_button("Edit Event"):
                    ss.edit_mode = True
                    st.rerun()

        # ── QR code ────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Event QR Code")
        qr_url = cache_bust(event.get("qr_code_image_url"))
        if qr_url:
            st.image(qr_url, width=300)
            qr_bytes = requests.get(qr_url).content
            st.download_button(
                "Download QR Code",
                data=qr_bytes,
                file_name=f"{event['code']}_qr.png",
                mime="image/png",
            )

    # ─── Tab 2 ─────────────────────────────────────────────────
    with tab_create:
        st.header("Create New Event")
        with st.form("create_form"):
            code = st.text_input("Event Code")
            name = st.text_input("Event Name")
            desc = st.text_area("Description")

            cols = st.columns(4)
            d0 = cols[0].date_input("Start Date", value=date.today())
            t0 = cols[1].time_input("Start Time", value=t(9, 0), step=1800)
            d1 = cols[2].date_input("End Date", value=date.today())
            t1 = cols[3].time_input("End Time", value=t(17, 0), step=1800)

            if st.form_submit_button("Create Event"):
                if not code.strip():
                    st.error("Event Code is required.")
                else:
                    try:
                        new = create_event(
                            event_code=code.strip(),
                            name=name or None,
                            description=desc or None,
                            start_date_time=datetime.combine(d0, t0),
                            end_date_time=datetime.combine(d1, t1),
                        )
                        st.success(f"Created '{new.get('name', new['code'])}'!")
                        ss.event_code = new["code"]
                        ss.just_created = True
                        st.rerun()
                    except requests.HTTPError as err:
                        st.error(f"Creation failed: {err}")
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")

        if ss.just_created:
            new_event = get_current_event(ss.event_code)
            if new_event and new_event.get("qr_code_image_url"):
                st.markdown("---")
                st.subheader("Your Event QR Code—save it!")
                qr_url = cache_bust(new_event["qr_code_image_url"])
                st.image(qr_url, width=300)
                qr_bytes = requests.get(qr_url).content
                st.download_button(
                    "Download QR Code",
                    data=qr_bytes,
                    file_name=f"{ss.event_code}_qr.png",
                    mime="image/png",
                )


if __name__ == "__main__":
    main()
