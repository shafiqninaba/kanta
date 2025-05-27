# pages/05_Manage_Events.py

from datetime import date, datetime, time  # For date/time manipulation
from typing import Optional

import streamlit as st
from utils.api import (
    create_event_api,
    get_events,
    update_event_api,
)  # Import new functions
from utils.session import get_event_selection, init_session_state

# --- Page Config ---
st.set_page_config(page_title="Event Management", page_icon="⚙️", layout="wide")

# --- Initialize Session State ---
init_session_state()  # Ensures common session state variables are set
ss = st.session_state
ss.setdefault("manage_events_edit_mode", False)
ss.setdefault(
    "manage_events_current_event_details", None
)  # To store details for editing


# --- Helper to parse datetime from API (handles None and string) ---
def parse_datetime_from_api(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
    except ValueError:
        return None  # Or raise error, or try other formats


# --- Helper to combine date and time from Streamlit inputs ---
def combine_date_time(
    input_date: Optional[date], input_time: Optional[time]
) -> Optional[datetime]:
    if input_date and input_time:
        return datetime.combine(input_date, input_time)
    elif input_date:  # If only date is provided, default time to midnight
        return datetime.combine(input_date, time.min)
    return None


# --- Main Page ---
st.title("Event Management")

# --- Load current event if selected in sidebar ---
# This uses the existing get_event_selection logic from your utils.session
# It sets ss.event_code, ss.event_name, ss.event_details
get_event_selection()  # Pass your API fetching function

# --- Tabs ---
tab1, tab2 = st.tabs(["📋 View & Edit Current Event", "➕ Create New Event"])

# =========================
# TAB 1: View & Edit Event
# =========================
with tab1:
    st.subheader("Current Event Details")

    if not ss.get("event_code"):
        st.info(
            "👉 Select an event from the sidebar to view or edit its details, or create a new event in the next tab."
        )
    else:
        # Fetch fresh details for the selected event for editing, or use sidebar's ss.event_details for display
        if (
            ss.manage_events_edit_mode
            or not ss.manage_events_current_event_details
            or ss.manage_events_current_event_details.get("code") != ss.event_code
        ):
            event_data_list = get_events(event_code=ss.event_code)
            if event_data_list:
                ss.manage_events_current_event_details = event_data_list[0]
            elif not event_data_list:
                st.error(
                    f"Could not find details for event code: {ss.event_code}. It might have been deleted."
                )
                ss.manage_events_current_event_details = None
                ss.event_code = None  # Clear invalid event code
            else:  # API call failed
                st.error(
                    f"Failed to fetch event details: {event_data_list}"
                )  # event_data_list is error message here
                ss.manage_events_current_event_details = None

        event = ss.manage_events_current_event_details

        if not event:
            st.warning("No event data loaded for editing. Try re-selecting the event.")
        else:
            # --- Display Form (View or Edit Mode) ---
            with st.form(key="view_edit_event_form"):
                st.text_input(
                    "Event Code (Read-only)", value=event.get("code", ""), disabled=True
                )

                name = st.text_input(
                    "Event Name",
                    value=event.get("name", ""),
                    disabled=not ss.manage_events_edit_mode,
                    placeholder="E.g., Summer Festival 2024",
                )
                description = st.text_area(
                    "Description",
                    value=event.get("description", ""),
                    disabled=not ss.manage_events_edit_mode,
                    placeholder="Details about the event...",
                )

                current_start_dt = parse_datetime_from_api(event.get("start_date_time"))
                current_end_dt = parse_datetime_from_api(event.get("end_date_time"))

                col_start_date, col_start_time, col_end_date, col_end_time = st.columns(
                    4
                )
                with col_start_date:
                    start_date = st.date_input(
                        "Start Date",
                        value=current_start_dt.date() if current_start_dt else None,
                        disabled=not ss.manage_events_edit_mode,
                    )
                with col_start_time:
                    start_time = st.time_input(
                        "Start Time",
                        value=current_start_dt.time()
                        if current_start_dt
                        else time(9, 0),  # Default to 9 AM
                        disabled=not ss.manage_events_edit_mode,
                        step=1800,  # 30 min steps
                    )
                with col_end_date:
                    end_date = st.date_input(
                        "End Date",
                        value=current_end_dt.date() if current_end_dt else None,
                        disabled=not ss.manage_events_edit_mode,
                    )
                with col_end_time:
                    end_time = st.time_input(
                        "End Time",
                        value=current_end_dt.time()
                        if current_end_dt
                        else time(17, 0),  # Default to 5 PM
                        disabled=not ss.manage_events_edit_mode,
                        step=1800,  # 30 min steps
                    )

                if not ss.manage_events_edit_mode:
                    st.caption(
                        f"Created At: {parse_datetime_from_api(event.get('created_at')).strftime('%Y-%m-%d %H:%M') if event.get('created_at') else 'N/A'}"
                    )
                    st.caption(
                        f"Currently Running: {'Yes' if event.get('running', False) else 'No'}"
                    )

                # --- Form Submission ---
                submitted_update = st.form_submit_button(
                    "💾 Save Changes" if ss.manage_events_edit_mode else "✏️ Edit Event"
                )

                if submitted_update:
                    if ss.manage_events_edit_mode:
                        # --- Save Logic ---
                        final_start_dt = combine_date_time(start_date, start_time)
                        final_end_dt = combine_date_time(end_date, end_time)

                        if (
                            final_start_dt
                            and final_end_dt
                            and final_start_dt >= final_end_dt
                        ):
                            st.error(
                                "Validation Error: Start date/time must be before end date/time."
                            )
                        else:
                            update_payload = {
                                "event_code": event["code"],  # Must include event_code
                                "name": name
                                if name != event.get("name")
                                else None,  # Send only if changed or explicitly set
                                "description": description
                                if description != event.get("description")
                                else None,
                                "start_date_time": final_start_dt.isoformat()
                                if final_start_dt
                                else None,
                                "end_date_time": final_end_dt.isoformat()
                                if final_end_dt
                                else None,
                            }
                            # Filter out None values so only provided fields are sent for update
                            update_payload = {
                                k: v
                                for k, v in update_payload.items()
                                if v is not None or k == "event_code"
                            }
                            # If only event_code is left, it means no actual changes were made by user to optional fields
                            if len(update_payload) <= 1 and not (
                                name or description or final_start_dt or final_end_dt
                            ):
                                st.info("No changes detected to save.")
                                ss.manage_events_edit_mode = False  # Exit edit mode
                                st.rerun()

                            else:
                                updated_event_data, success, error_msg = (
                                    update_event_api(update_payload)
                                )
                                if success:
                                    st.success("✅ Event updated successfully!")
                                    ss.manage_events_current_event_details = (
                                        updated_event_data  # Update displayed details
                                    )
                                    ss.manage_events_edit_mode = False  # Exit edit mode
                                    # Crucially, update the sidebar's event list and selected event if name changed
                                    ss.event_name = updated_event_data.get(
                                        "name"
                                    )  # Update name for sidebar display
                                    ss.event_details = (
                                        updated_event_data  # Update full details
                                    )
                                    # Force sidebar to re-fetch events if desired, or update ss.events_list
                                    st.rerun()  # Rerun to refresh display and sidebar
                                else:
                                    st.error(f"⚠️ Update failed: {error_msg}")
                    else:
                        # --- Toggle to Edit Mode ---
                        ss.manage_events_edit_mode = True
                        st.rerun()  # Rerun to enable fields

            if ss.manage_events_edit_mode:
                if st.button("✖️ Cancel Edit", key="cancel_edit_btn"):
                    ss.manage_events_edit_mode = False
                    # Optionally, revert form fields to original by re-fetching or using a snapshot
                    # For simplicity, just exiting edit mode will show original values on next rerun if not saved
                    st.rerun()

# =========================
# TAB 2: Create New Event
# =========================
with tab2:
    st.subheader("Create a New Event")
    with st.form(key="create_event_form"):
        new_event_code = st.text_input(
            "Unique Event Code*",
            help="Alphanumeric and underscores only, e.g., 'MY_EVENT_24'",
        )
        new_name = st.text_input(
            "Event Name", placeholder="E.g., Annual Company Picnic"
        )
        new_description = st.text_area(
            "Description", placeholder="Further details about the new event."
        )

        st.markdown("###### Event Duration (Optional)")
        new_col_start_date, new_col_start_time, new_col_end_date, new_col_end_time = (
            st.columns(4)
        )
        with new_col_start_date:
            new_start_date = st.date_input(
                "Start Date", value=None, key="create_start_d"
            )
        with new_col_start_time:
            new_start_time = st.time_input(
                "Start Time", value=time(9, 0), key="create_start_t", step=1800
            )
        with new_col_end_date:
            new_end_date = st.date_input("End Date", value=None, key="create_end_d")
        with new_col_end_time:
            new_end_time = st.time_input(
                "End Time", value=time(17, 0), key="create_end_t", step=1800
            )

        submitted_create = st.form_submit_button("🚀 Create Event")

        if submitted_create:
            if not new_event_code:
                st.error("Event Code is required.")
            else:
                final_new_start_dt = combine_date_time(new_start_date, new_start_time)
                final_new_end_dt = combine_date_time(new_end_date, new_end_time)

                if (
                    final_new_start_dt
                    and final_new_end_dt
                    and final_new_start_dt >= final_new_end_dt
                ):
                    st.error(
                        "Validation Error: Start date/time must be before end date/time."
                    )
                else:
                    create_payload = {
                        "event_code": new_event_code,
                        "name": new_name if new_name else None,
                        "description": new_description if new_description else None,
                        "start_date_time": final_new_start_dt.isoformat()
                        if final_new_start_dt
                        else None,
                        "end_date_time": final_new_end_dt.isoformat()
                        if final_new_end_dt
                        else None,
                    }
                    # Filter out None values for optional fields, but keep event_code
                    create_payload = {
                        k: v
                        for k, v in create_payload.items()
                        if v is not None or k == "event_code"
                    }

                    created_event_data, success, error_msg = create_event_api(
                        create_payload
                    )
                    if success and created_event_data:
                        st.success(
                            f"✅ Event '{created_event_data.get('name', created_event_data['code'])}' created successfully!"
                        )
                        # Update sidebar to select this new event
                        ss.event_code = created_event_data["code"]
                        ss.event_name = created_event_data.get("name")
                        ss.event_details = created_event_data
                        ss.manage_events_edit_mode = (
                            False  # Ensure view mode on other tab
                        )
                        ss.manage_events_current_event_details = (
                            created_event_data  # Load for view tab
                        )
                        # Force a re-fetch for the sidebar's event list
                        # This could be done by clearing ss.events_list if your get_event_selection uses it
                        if "events_list" in ss:
                            del ss["events_list"]
                        st.rerun()  # Rerun to update sidebar and switch view
                    else:
                        st.error(f"⚠️ Creation failed: {error_msg}")
