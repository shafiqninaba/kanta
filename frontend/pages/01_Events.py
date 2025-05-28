import streamlit as st
from datetime import datetime, date, time
from typing import Dict, Any

from utils.session import get_event_selection, init_session_state
from utils.api import get_events, update_event_api, create_event_api, ApiError

# --- Page Config ---
st.set_page_config(page_title="Events 🎭", page_icon="🎭", layout="wide")


def main() -> None:
    """
    Event Management page with two tabs:
      1. Current Event: unified view/edit form
      2. Create New Event
    """
    init_session_state()
    get_event_selection()
    ss = st.session_state
    ss.setdefault("edit_mode", False)

    st.title("🎭 Events")
    tab_current, tab_create = st.tabs(["Current Event", "Create New Event"])

    # --- Current Event Tab ---
    with tab_current:
        st.subheader("Current Event")
        if not ss.get("event_code"):
            st.warning("Please select or create an event first.")
        else:
            try:
                event = get_events(event_code=ss.event_code)[0]
            except ApiError as err:
                st.error(f"Error fetching event: {err}")
                return

            # Parse datetimes
            start_dt = (
                datetime.fromisoformat(event["start_date_time"].replace("Z", "+00:00"))
                if event.get("start_date_time")
                else None
            )
            end_dt = (
                datetime.fromisoformat(event["end_date_time"].replace("Z", "+00:00"))
                if event.get("end_date_time")
                else None
            )

            # Unified form
            with st.form(key="event_form"):
                st.text_input("Event Code", value=event["code"], disabled=True)
                name = st.text_input(
                    "Event Name", value=event.get("name", ""), disabled=not ss.edit_mode
                )
                description = st.text_area(
                    "Description",
                    value=event.get("description", ""),
                    disabled=not ss.edit_mode,
                )
                cols = st.columns(4)
                d0 = cols[0].date_input(
                    "Start Date",
                    value=start_dt.date() if start_dt else date.today(),
                    disabled=not ss.edit_mode,
                )
                t0 = cols[1].time_input(
                    "Start Time",
                    value=start_dt.time() if start_dt else time(9, 0),
                    step=1800,
                    disabled=not ss.edit_mode,
                )
                d1 = cols[2].date_input(
                    "End Date",
                    value=end_dt.date() if end_dt else date.today(),
                    disabled=not ss.edit_mode,
                )
                t1 = cols[3].time_input(
                    "End Time",
                    value=end_dt.time() if end_dt else time(17, 0),
                    step=1800,
                    disabled=not ss.edit_mode,
                )

                # Action buttons
                if ss.edit_mode:
                    save, cancel = st.columns(2)
                    if save.form_submit_button("💾 Save"):
                        try:
                            payload: Dict[str, Any] = {
                                "event_code": event["code"],
                                "name": name,
                                "description": description,
                                "start_date_time": datetime.combine(d0, t0).isoformat(),
                                "end_date_time": datetime.combine(d1, t1).isoformat(),
                            }
                            update_event_api(payload)
                            st.success("Event updated successfully!")
                            ss.edit_mode = False
                            st.rerun()
                        except ApiError as err:
                            st.error(f"Update failed: {err}")
                    if cancel.form_submit_button("✖️ Cancel"):
                        ss.edit_mode = False
                        st.rerun()
                else:
                    if st.form_submit_button("Edit Event"):
                        ss.edit_mode = True
                        st.rerun()

    # --- Create New Event Tab ---
    with tab_create:
        st.subheader("Create New Event")
        with st.form(key="create_event_form"):
            event_code = st.text_input(
                "Event Code *",
                placeholder="E.g., MY_EVENT_24",
                help="Must be unique and alphanumeric (letters, numbers, underscores).",
            )
            name_in = st.text_input(
                "Event Name",
                placeholder="My Awesome Event",
                help="Optional name for the event.",
            )
            desc_in = st.text_area("Description", placeholder="Awesome event details...", help="Optional description of the event.")

            # Date and time inputs
            cols = st.columns(4)
            d0 = cols[0].date_input("Start Date", value=date.today())
            t0 = cols[1].time_input("Start Time", value=time(9, 0), step=1800)
            d1 = cols[2].date_input("End Date", value=date.today())
            t1 = cols[3].time_input("End Time", value=time(17, 0), step=1800)
            if st.form_submit_button("Create Event"):
                if not event_code:
                    st.error("Event Code is required.")
                else:
                    try:
                        payload: Dict[str, Any] = {
                            "event_code": event_code.strip(),
                            "name": name_in or None,
                            "description": desc_in or None,
                            "start_date_time": datetime.combine(d0, t0).isoformat(),
                            "end_date_time": datetime.combine(d1, t1).isoformat(),
                        }
                        created = create_event_api(payload)
                        st.success(
                            f"Event '{created.get('name', created['code'])}' created!"
                        )
                        ss.event_code = created.get("code")
                        st.rerun()
                    except ApiError as err:
                        st.error(f"Creation failed: {err}")


if __name__ == "__main__":
    main()
