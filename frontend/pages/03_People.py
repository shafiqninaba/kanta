import streamlit as st
from PIL import Image, UnidentifiedImageError
import requests
from io import BytesIO
import base64
import json

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


# --- Helper Function to fetch image bytes ---
@st.cache_data(ttl=3600)
def fetch_image_bytes_from_url(image_url: str) -> BytesIO | None:
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        return BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        st.sidebar.error(
            f"Error fetching image: {image_url[:50]}... Details in console."
        )
        print(f"Error fetching image data from {image_url[:60]}...: {e}")
        return None


# --- Helper Function to Crop and Encode Face ---
def crop_and_encode_face(
    full_image_bytes_io: BytesIO, bbox: dict, target_size: tuple
) -> str | None:
    try:
        img = Image.open(full_image_bytes_io)
        x, y, w, h = (
            int(bbox["x"]),
            int(bbox["y"]),
            int(bbox["width"]),
            int(bbox["height"]),
        )

        pad_w, pad_h = int(w * 0.2), int(h * 0.2)
        crop_box = (
            max(0, x - pad_w),
            max(0, y - pad_h),
            min(img.width, x + w + pad_w),
            min(img.height, y + h + pad_h),
        )
        face_img = img.crop(crop_box)
        face_img.thumbnail(target_size, Image.Resampling.LANCZOS)

        canvas = Image.new("RGB", target_size, (255, 255, 255))
        paste_x = (target_size[0] - face_img.width) // 2
        paste_y = (target_size[1] - face_img.height) // 2
        canvas.paste(face_img, (paste_x, paste_y))

        buffered = BytesIO()
        canvas.save(buffered, format="PNG")
        base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{base64_str}"
    except UnidentifiedImageError:
        print(f"Error: Could not identify image for bbox {bbox}")
    except Exception as e:
        print(f"Error cropping/encoding face with bbox {bbox}: {e}")
    return None


# --- Main Application ---
st.title("People")
st.markdown(
    "Discover unique individuals detected in the event images. "
    "Each circle represents a person, showing sample faces. Click 'View Images' to see all photos of that person."
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

st.markdown("---")  # Separator

# --- Removed Central Navigation Button ---
# The navigation will now be per-person card.

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
        for sample_idx, sample in enumerate(
            samples
        ):  # Added sample_idx for more robust key generation if needed
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
            "js_image_id": f"person_img_{cluster_id}_{person_idx}",  # Added person_idx for guaranteed unique js_image_id
        }
    )

# --- Display Identified People in a Grid ---
if not person_clusters_data:
    st.info("No identified people to display for this event yet.")
elif not people_display_data and person_clusters_data:
    st.info(
        "Identified people found, but no sample faces could be prepared for display."
    )
else:
    st.subheader(f"Identified People: {len(people_display_data)}")
    grid_cols = st.columns(PERSON_CARD_COLS)
    for i, person_display in enumerate(people_display_data):
        with grid_cols[i % PERSON_CARD_COLS]:
            js_image_list = json.dumps(person_display["sample_face_data_urls"])

            # HTML for the image and label part of the card
            person_card_content_html = f"""
            <div class="person-card-visuals"> 
                <img id="{person_display['js_image_id']}" 
                     src="{person_display['initial_face_url']}" 
                     class="person-face-circle" 
                     alt="Person {person_display['display_id']}" 
                     title="Person {person_display['display_id']}: {person_display['item_count']} items">
                <p class="person-label">Person {person_display['display_id']}: {person_display['item_count']} items</p>
            </div>
            <script>
                // Image cycling script
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

            # --- Centered Button for this specific person ---
            button_key = f"view_person_btn_{person_display['original_cluster_id']}_{i}"

            # Use 3 columns to center the button.
            # The middle column will contain the button.
            # Adjust ratios: [spacer_left, button_content, spacer_right]
            # e.g., [1, 1.5, 1] means the button column is 1.5 times the width of spacers.
            # If the button text is short, a ratio like [1,1,1] might also work well,
            # or even [0.5, 1, 0.5] if you want less aggressive spacing on sides.
            # Let's try [1, 1.2, 1] for a moderately sized center column for the button.
            _col_spacer_left, col_button_center, _col_spacer_right = st.columns(
                [1, 1.2, 1]
            )

            with col_button_center:
                if st.button(
                    "View Images",
                    key=button_key,
                    type="primary",  # This should make it blue
                    use_container_width=True,  # Make button fill the middle column
                ):
                    ss.browse_filter_cluster_id = person_display["original_cluster_id"]
                    ss.gallery_page = 1
                    st.switch_page("pages/02_Gallery.py")

# --- Display Unassigned and Processing Information ---
st.markdown("---")

# Display Unassigned Faces Information (if any)
if unassigned_info:
    count = unassigned_info.get("face_count", 0)
    samples = unassigned_info.get("samples", [])

    st.subheader(f"Unidentified People: {count}")  # Display count in subheader
    expander_title = "Click to view samples"
    if count == 0:
        expander_title = "No unidentified faces"
    elif not samples:
        expander_title = f"{count} unidentified (no samples available)"

    with st.expander(
        expander_title, expanded=(count > 0 and len(samples) > 0)
    ):  # Expand if there's something to show
        if count > 0 and not samples:
            st.write("Samples for unidentified faces are not available at the moment.")
        elif count == 0:
            st.write("No unidentified faces found.")
        elif not samples:  # Should be caught by above, but as a fallback
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
elif (
    person_clusters_data
):  # Only show this if there were identified people but no unassigned cluster
    st.subheader("Unidentified People: 0")
    st.info("No faces are currently marked as unidentified for this event.")

# Display Processing Information (if any)
if processing_info:
    count = processing_info.get("face_count", 0)
    if count > 0:  # Only show if there are faces being processed
        st.markdown("---")  # Separator
        st.info(
            f"**{count} faces are currently being processed** for person identification and are not yet categorized."
        )


# --- Custom CSS ---
st.markdown(
    f"""
<style>
    /* Styles for the container of image and label within each card */
    .person-card-visuals {{
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        margin-bottom: 10px; /* Space between visuals and button */
    }}
    .person-face-circle {{
        width: {SAMPLE_FACE_DISPLAY_SIZE[0]}px;
        height: {SAMPLE_FACE_DISPLAY_SIZE[1]}px;
        border-radius: 50%;
        object-fit: cover;
        border: 3px solid #f0f2f6;
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
        font-size: 1.0em;
        margin-bottom: 0px; /* Reduced bottom margin for label */
        color: #333;
    }}

    /* Ensure Streamlit columns (acting as cards) have some bottom margin */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"] {{
        margin-bottom: 20px; /* Add some space below each card (column content) */
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
