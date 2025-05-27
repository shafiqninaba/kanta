import streamlit as st
from PIL import Image, UnidentifiedImageError
import requests
from io import BytesIO
import base64
import json
from utils.image_helpers import fetch_image_bytes_from_url, crop_and_encode_face

from utils.api import get_clusters  # Assuming this is in utils.api
from utils.session import get_event_selection, init_session_state

# --- Page Configuration ---
st.set_page_config(page_title="People", page_icon="🧑‍🤝‍🧑", layout="wide")

# --- Initialize Session State & Event Selection ---
init_session_state()
get_event_selection()

# --- Constants ---
PERSON_CARD_COLS = 4
SAMPLE_FACE_DISPLAY_SIZE = (150, 150)
SWAP_INTERVAL_MS = 20000

# --- Session State for this page ---
ss = st.session_state
ss.setdefault("people_sample_size", 5)
ss.setdefault(
    "people_selected_clusters", {}
)  # Stores {cluster_id: True/False} for selection

# --- Main Application ---
st.title("People")
st.markdown(
    "Select individuals from the list below to view images containing them. "
    "Each circle represents a person, showing sample faces."
)

if not ss.get("event_code"):
    st.warning("👈 Please select an event from the sidebar to view identified people.")
    st.stop()

# --- Controls ---
new_sample_size = st.slider(
    "Sample faces per person to display",
    min_value=1,
    max_value=10,
    value=ss.people_sample_size,
    key="people_sample_size_slider",
    help="Number of sample faces to fetch and cycle through for each person.",
)
if new_sample_size != ss.people_sample_size:
    ss.people_sample_size = new_sample_size
    # Clear previous selections if sample size changes, as the list of people might change
    ss.people_selected_clusters = {}


st.markdown("---")

# --- Fetch and Process Data ---
with st.spinner(f"Loading people data with {ss.people_sample_size} samples each..."):
    all_clusters_data, success = get_clusters(ss.event_code, ss.people_sample_size)

if not success:
    st.error(f"Failed to load people data: {all_clusters_data}")
    st.stop()

if not all_clusters_data:
    st.info("No people data found for this event, or processing might not be complete.")
    st.stop()

processing_info = None
unassigned_info = None
person_clusters_data = []

for cluster in all_clusters_data:
    cluster_id = cluster.get("cluster_id")
    if cluster_id == -2:
        processing_info = cluster
    elif cluster_id == -1:
        unassigned_info = cluster
    elif cluster_id is not None and cluster_id >= 0:
        person_clusters_data.append(cluster)

people_display_data = []
for person_idx, cluster_info in enumerate(person_clusters_data):
    cluster_id = cluster_info.get("cluster_id")
    item_count = cluster_info.get("face_count", 0)
    samples = cluster_info.get("samples", [])
    cropped_sample_face_urls = []
    if samples:
        for sample_idx, sample in enumerate(samples):
            full_image_url = sample.get("sample_blob_url")
            bbox = sample.get("sample_bbox")
            if full_image_url and isinstance(bbox, dict):
                full_image_bytes = fetch_image_bytes_from_url(full_image_url)
                if full_image_bytes:
                    encoded_face = crop_and_encode_face(
                        full_image_bytes, bbox, SAMPLE_FACE_DISPLAY_SIZE
                    )
                    if encoded_face:
                        cropped_sample_face_urls.append(encoded_face)
    initial_face_url = (
        cropped_sample_face_urls[0]
        if cropped_sample_face_urls
        else "https://via.placeholder.com/150/CCCCCC/808080?text=No+Sample"
    )
    people_display_data.append(
        {
            "original_cluster_id": cluster_id,
            "display_id": person_idx,
            "item_count": item_count,
            "initial_face_url": initial_face_url,
            "sample_face_data_urls": cropped_sample_face_urls,
            "js_image_id": f"person_img_{cluster_id}_{person_idx}",
        }
    )

# --- Display Identified People in a Grid with Selection ---
if not person_clusters_data:
    st.info("No identified people to display for this event yet.")
elif not people_display_data and person_clusters_data:
    st.info(
        "Identified people found, but no sample faces could be prepared for display."
    )
else:
    st.subheader(f"Identified People: {len(people_display_data)}")
    st.markdown("Select one or more people below:")

    grid_cols = st.columns(PERSON_CARD_COLS)
    for i, person_display in enumerate(people_display_data):
        with grid_cols[i % PERSON_CARD_COLS]:
            cluster_id = person_display["original_cluster_id"]
            js_image_list = json.dumps(person_display["sample_face_data_urls"])

            # Checkbox for selection
            # The value comes from session state to persist selections across reruns
            is_person_selected = st.checkbox(
                f"Select Person {person_display['display_id']}",
                value=ss.people_selected_clusters.get(cluster_id, False),
                key=f"select_person_{cluster_id}_{i}",
                label_visibility="collapsed",  # Hide label, use card visuals
            )
            # Update session state based on checkbox interaction
            ss.people_selected_clusters[cluster_id] = is_person_selected

            # Visual indication of selection on the card itself (optional)
            border_style = (
                "border: 3px solid #007bff;"
                if is_person_selected
                else "border: 3px solid #f0f2f6;"
            )

            person_card_content_html = f"""
            <div class="person-card-visuals" style="{border_style} padding: 5px; border-radius: 8px;"> 
                <img id="{person_display['js_image_id']}" 
                     src="{person_display['initial_face_url']}" 
                     class="person-face-circle" 
                     alt="Person {person_display['display_id']}" 
                     title="Person {person_display['display_id']}: {person_display['item_count']} items. Click checkbox above to select.">
                <p class="person-label">Person {person_display['display_id']} ({person_display['item_count']})</p>
            </div>
            <script>
                if (!document.getElementById("{person_display['js_image_id']}").dataset.swapperActive) {{
                    let images_{person_display['js_image_id']} = {js_image_list};
                    let currentIndex_{person_display['js_image_id']} = 0;
                    let imgElement_{person_display['js_image_id']} = document.getElementById("{person_display['js_image_id']}");
                    if (imgElement_{person_display['js_image_id']} && images_{person_display['js_image_id']}.length > 1) {{
                        setInterval(function() {{
                            currentIndex_{person_display['js_image_id']} = (currentIndex_{person_display['js_image_id']} + 1) % images_{person_display['js_image_id']}.length;
                            imgElement_{person_display['js_image_id']}.src = images_{person_display['js_image_id']}[currentIndex_{person_display['js_image_id']}];
                        }}, {SWAP_INTERVAL_MS});
                        imgElement_{person_display['js_image_id']}.dataset.swapperActive = 'true';
                    }} else if (imgElement_{person_display['js_image_id']}) {{
                        imgElement_{person_display['js_image_id']}.dataset.swapperActive = 'true';
                    }}
                }}
            </script>
            """
            st.markdown(person_card_content_html, unsafe_allow_html=True)

    # Button to View Images of Selected People - Placed above the grid
    selected_ids_for_button = [
        cid for cid, selected in ss.people_selected_clusters.items() if selected
    ]

    # Use columns to make the button not full width
    col_btn_left, col_btn_mid, col_btn_right = st.columns([1, 1.5, 1])
    with col_btn_mid:
        if st.button(
            f"View Images of Selected ({len(selected_ids_for_button)}) People",
            key="view_selected_people_btn",
            type="primary",
            disabled=not selected_ids_for_button,
            use_container_width=True,
        ):
            ss.gallery_filter_cluster_list = (
                selected_ids_for_button  # Store list for gallery
            )
            ss.gallery_page = 1  # Reset gallery page
            # Clear other gallery filters if you want a fresh view for these clusters
            ss.gallery_date_from = None
            ss.gallery_date_to = None
            ss.gallery_min_faces = 0
            ss.gallery_max_faces = 0
            st.switch_page("pages/03_Gallery.py")  # Corrected page name

    st.markdown("---")  # Separator after button

# --- Display Unassigned and Processing Information (remains the same) ---
st.markdown("---")
if unassigned_info:
    count = unassigned_info.get("face_count", 0)
    samples = unassigned_info.get("samples", [])
    st.subheader(f"Unidentified People: {count}")
    expander_title = "Click to view samples"
    if count == 0:
        expander_title = "No unidentified faces"
    elif not samples:
        expander_title = f"{count} unidentified (no samples available)"

    with st.expander(expander_title, expanded=(count > 0 and len(samples) > 0)):
        if count > 0 and not samples:
            st.write("Samples for unidentified faces are not available at the moment.")
        elif count == 0:
            st.write("No unidentified faces found.")
        elif not samples:
            st.write("No samples to display for unidentified faces.")
        else:
            unassigned_face_urls = []
            for sample in samples:
                full_image_url = sample.get("sample_blob_url")
                bbox = sample.get("sample_bbox")
                if full_image_url and isinstance(bbox, dict):
                    full_image_bytes = fetch_image_bytes_from_url(full_image_url)
                    if full_image_bytes:
                        encoded_face = crop_and_encode_face(
                            full_image_bytes, bbox, (80, 80)
                        )
                        if encoded_face:
                            unassigned_face_urls.append(encoded_face)
            if not unassigned_face_urls:
                st.write("Could not process samples for unidentified faces.")
            else:
                cols_per_row = min(8, len(unassigned_face_urls))
                if cols_per_row > 0:
                    img_cols = st.columns(cols_per_row)
                    for i, face_url in enumerate(unassigned_face_urls):
                        img_cols[i % cols_per_row].image(face_url, width=80)
elif person_clusters_data:
    st.subheader("Unidentified People: 0")
    st.info("No faces are currently marked as unidentified for this event.")
if processing_info:
    count = processing_info.get("face_count", 0)
    if count > 0:
        st.markdown("---")
        st.info(
            f"**{count} faces are currently being processed** for person identification and are not yet categorized."
        )

# --- Custom CSS ---
st.markdown(
    f"""
<style>
    .person-card-visuals {{
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        margin-bottom: 10px; 
    }}
    .person-face-circle {{
        width: {SAMPLE_FACE_DISPLAY_SIZE[0]}px;
        height: {SAMPLE_FACE_DISPLAY_SIZE[1]}px;
        border-radius: 50%;
        object-fit: cover;
        /* border removed here, applied dynamically via style attribute */
        margin-bottom: 10px;
        background-color: #e0e0e0;
        transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
    }}
    .person-face-circle:hover {{
        transform: scale(1.05);
        box-shadow: 0px 4px 12px rgba(0,0,0,0.15);
    }}
    .person-label {{
        font-weight: bold;
        font-size: 0.9em; /* Slightly smaller label */
        margin-bottom: 0px; 
        color: #333;
        white-space: nowrap; /* Prevent wrapping for short labels */
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
    }}
    div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"] {{
        padding-bottom: 15px; 
        margin-bottom: 20px; 
    }}
    /* Ensure checkboxes are somewhat aligned with the card content */
    div[data-testid="stCheckbox"] {{
        display: flex;
        justify-content: center; /* Center the checkbox itself */
        padding-top: 5px;      /* Space above checkbox */
        padding-bottom: 5px;   /* Space below checkbox before image card */
    }}
    div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] div[data-testid="stImage"] img {{
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid #ddd;
    }}
</style>
""",
    unsafe_allow_html=True,
)
