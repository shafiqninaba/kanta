import streamlit as st
from utils.session import get_event_selection, init_session_state


st.set_page_config(
    page_title="Kanta Event Photos",  # Updated title
    page_icon="📸",  # Changed icon to a camera
    layout="wide",
)

# Initialize session state (ensures common variables like event_code exist)
init_session_state()

# Display sidebar with event selection
get_event_selection()

# Main content for home page
st.title("📸 Kanta - Collaborative Event Photos")  # Updated title

st.markdown("""
    ### Welcome to Kanta!
    
    Kanta helps you and your guests capture and organize photos from any event. 
    It's like a shared digital camera roll that automatically identifies people and groups their photos together, 
    making it easy to find every moment.
""")

st.markdown("---")

# Check if event is selected
if not st.session_state.get("event_code"):  # Use .get for safer access
    st.warning(
        "👈 Please select an event from the sidebar, or create a new one in 'Event Management' to get started!"
    )
    st.page_link("pages/01_Event_Management", label="Go to Event Management", icon="⚙️")

else:
    event_name_display = st.session_state.get("event_name", st.session_state.event_code)
    st.success(
        f"🎉 You're currently viewing event: **{event_name_display}** (`{st.session_state.event_code}`)"
    )
    st.markdown(
        "Use the navigation menu on the left to explore the event's photos and features."
    )

st.markdown("---")

st.subheader("How to Use Kanta:")
st.markdown("""
    1.  **Event Setup (Admin)**:
        *   Navigate to **[01 Event Management](01_Event_Management)** to create a new event or manage existing ones. 
        *   Set the event name, description, and duration. You'll get a unique Event Code.

    2.  **Capture & Upload Photos**:
        *   During the event, use the **[02 Camera & Upload](02_Camera_Upload)** page (or share the Event Code with guests for them to upload).
        *   Easily upload photos from your phone or computer, or take new ones directly if your device supports it.

    3.  **Browse & Explore**:
        *   Go to **[03 Image Gallery](03_Image_Gallery)** to see all uploaded photos. Filter by date, number of faces, or specific people.
        *   Download your favorite shots individually or as a batch.

    4.  **Discover People**:
        *   Visit **[04 People & Similarity](04_People_Similarity)** to see who Kanta has automatically identified. 
        *   Select people to view all photos they appear in, or use the similarity search to find someone by uploading an example photo.
""")

st.markdown("---")
st.caption("Kanta: Capturing memories, together.")

if not st.session_state.get("event_code"):
    if st.button("Create or Select an Event First"):
        st.switch_page(
            "pages/01_Event_Management"
        )  # Or your event management page filename
