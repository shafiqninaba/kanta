# pages/04_People.py (or your chosen filename)

import base64
import json
from io import BytesIO

import streamlit as st
from PIL import Image, UnidentifiedImageError

# Ensure get_clusters and the new find_similar_faces_api are imported
from utils.api import find_similar_faces, get_clusters
from utils.image_helpers import crop_and_encode_face, fetch_image_bytes_from_url
from utils.session import get_event_selection, init_session_state

# --- Page Configuration ---
st.set_page_config(page_title="People & Similarity", page_icon="🧑‍🤝‍🧑", layout="wide")

# --- Initialize Session State & Event Selection ---
init_session_state()
# Pass the correct function to fetch events for the sidebar

get_event_selection()
CLUSTER_ID_UNASSIGNED = -1
CLUSTER_ID_PROCESSING = -2

# --- Constants ---
PERSON_CARD_COLS = 4  # For both identified people and similar faces display
SAMPLE_FACE_DISPLAY_SIZE = (150, 150)  # For identified people cards
SIMILAR_FACE_DISPLAY_SIZE = (120, 120)  # Slightly smaller for similarity results
SWAP_INTERVAL_MS = 20000

# --- Session State for this page ---
ss = st.session_state
ss.setdefault("people_sample_size", 1)
ss.setdefault("people_selected_clusters", {})
ss.setdefault("similarity_top_k", 10)
ss.setdefault("similarity_metric", "cosine")
ss.setdefault("similarity_results", None)  # To store results from API
ss.setdefault("similarity_query_image_b64", None)  # To display the uploaded query image

# --- Main Application ---
st.title("People & Similarity Search")


if not ss.get("event_code"):
    st.warning("👈 Please select an event from the sidebar to use these features.")
    st.stop()

# --- Tabs ---
tab_identified, tab_similarity = st.tabs(
    ["👥 Identified People", "🔍 Find Similar Faces"]
)

# =================================
# TAB 1: IDENTIFIED PEOPLE
# =================================
with tab_identified:
    st.markdown(
        "Select individuals from the list below to view images containing them. "
        "Each circle represents a person, showing sample faces."
    )
    new_sample_size = st.slider(
        "Sample faces per person (Identified People)",
        min_value=1,
        max_value=10,
        value=ss.people_sample_size,
        key="people_sample_size_slider_tab1",  # Unique key
    )
    if new_sample_size != ss.people_sample_size:
        ss.people_sample_size = new_sample_size
        ss.people_selected_clusters = {}  # Reset selection if samples change

    st.markdown("---")

    # Fetch and Process Data for Identified People
    with st.spinner(
        f"Loading identified people with {ss.people_sample_size} samples each..."
    ):
        all_clusters_data = get_clusters(ss.event_code, ss.people_sample_size)

    if not all_clusters_data:
        st.error(f"Failed to load identified people data: {all_clusters_data}")
    elif not all_clusters_data:
        st.info(
            "No identified people data found for this event, or processing might not be complete."
        )
    else:
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

        if not person_clusters_data:
            st.info("No identified people to display for this event yet.")
        elif not people_display_data and person_clusters_data:
            st.info(
                "Identified people found, but no sample faces could be prepared for display."
            )
        else:
            st.subheader(f"Identified People: {len(people_display_data)}")
            st.markdown("Select one or more people below to filter the gallery:")

            grid_cols_identified = st.columns(PERSON_CARD_COLS)
            for i, person_display in enumerate(people_display_data):
                with grid_cols_identified[i % PERSON_CARD_COLS]:
                    cluster_id = person_display["original_cluster_id"]
                    js_image_list = json.dumps(person_display["sample_face_data_urls"])
                    is_person_selected = st.checkbox(
                        f"Select Person {person_display['display_id']}",
                        value=ss.people_selected_clusters.get(cluster_id, False),
                        key=f"select_person_tab1_{cluster_id}_{i}",  # Unique key
                        label_visibility="collapsed",
                    )
                    ss.people_selected_clusters[cluster_id] = is_person_selected
                    border_style = (
                        "border: 3px solid #007bff;"
                        if is_person_selected
                        else "border: 3px solid #f0f2f6;"
                    )
                    person_card_html = f"""
                    <div class="person-card-visuals" style="{border_style} padding: 5px; border-radius: 8px;"> 
                        <img id="{person_display['js_image_id']}" src="{person_display['initial_face_url']}" 
                             class="person-face-circle" alt="Person {person_display['display_id']}" 
                             title="Person {person_display['display_id']}: {person_display['item_count']} items. Check box above to select.">
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
                    </script>"""
                    st.markdown(person_card_html, unsafe_allow_html=True)

            selected_ids_for_button = [
                cid for cid, sel in ss.people_selected_clusters.items() if sel
            ]
            col_btn_left1, col_btn_mid1, col_btn_right1 = st.columns([1, 1.5, 1])
            with col_btn_mid1:
                if st.button(
                    f"🖼️ View Images of Selected ({len(selected_ids_for_button)}) People",
                    key="view_selected_tab1_btn",
                    type="primary",
                    disabled=not selected_ids_for_button,
                    use_container_width=True,
                ):
                    ss.gallery_filter_cluster_list = selected_ids_for_button
                    ss.gallery_page = 1
                    ss.gallery_date_from = None
                    ss.gallery_date_to = None
                    ss.gallery_min_faces = 0
                    ss.gallery_max_faces = 0
                    st.switch_page(
                        "pages/03_Gallery.py"
                    )  # Ensure this is your correct gallery page filename
            st.markdown("---")

    # --- Display Unassigned and Processing Information ---
    if unassigned_info:
        count = unassigned_info.get("face_count", 0)
        samples = unassigned_info.get("samples", [])  # samples is a list

        st.subheader(f"Unidentified People: {count}")

        # Determine expander title
        if count == 0:
            exp_title = "No unidentified faces"
        elif not samples:  # samples is an empty list
            exp_title = f"{count} unidentified (no samples available)"
        else:  # samples is a non-empty list
            exp_title = f"View up to {len(samples)} samples of {count} unidentified"

        # CORRECTED expanded condition:
        with st.expander(exp_title, expanded=(count > 0 and len(samples) > 0)):
            if count > 0 and not samples:  # No samples but count > 0
                st.write(
                    "Samples for unidentified faces are not available at the moment."
                )
            elif count == 0:  # No unidentified faces at all
                st.write("No unidentified faces found.")
            # This 'elif not samples:' might be redundant now given the title logic, but safe
            elif not samples:
                st.write("No samples to display for unidentified faces.")
            else:  # We have samples and count > 0
                unassigned_urls = []
                for sample_item in samples:  # Renamed 'sample' to 'sample_item' to avoid conflict if 'samples' was used differently
                    img_url = sample_item.get("sample_blob_url")
                    bbox = sample_item.get("sample_bbox")
                    if img_url and isinstance(bbox, dict):  # Ensure bbox is a dict
                        img_bytes = fetch_image_bytes_from_url(img_url)
                        if img_bytes:
                            face_b64 = crop_and_encode_face(img_bytes, bbox, (80, 80))
                            if face_b64:
                                unassigned_urls.append(face_b64)

                if unassigned_urls:
                    cols_per_row_unassigned = min(
                        8, len(unassigned_urls)
                    )  # Dynamic columns
                    if cols_per_row_unassigned > 0:
                        img_cols_unassigned = st.columns(cols_per_row_unassigned)
                        for i, url in enumerate(unassigned_urls):
                            img_cols_unassigned[i % cols_per_row_unassigned].image(
                                url, width=80
                            )
                else:
                    st.write("No samples could be processed or displayed.")
    elif (
        person_clusters_data
    ):  # Only show this if identified people existed but no unassigned_info cluster
        st.subheader("Unidentified People: 0")
        st.info("No faces are currently marked as unidentified for this event.")

    if processing_info:
        count = processing_info.get("face_count", 0)
        if count > 0:
            st.markdown(
                "---"
            )  # Add separator if both unassigned and processing are shown
            st.info(
                f"⚙️ **{count} faces are currently being processed** and are not yet categorized."
            )


# =================================
# TAB 2: SIMILARITY SEARCH
# =================================
with tab_similarity:
    st.subheader("Find Similar Faces by Example")
    st.markdown(
        "Upload an image containing a single clear face. The system will search for the most similar faces within this event."
    )

    sim_cols_controls = st.columns([2, 1, 1])
    with sim_cols_controls[0]:
        uploaded_file = st.file_uploader(
            "Upload face image", type=["jpg", "jpeg", "png"], key="similarity_uploader"
        )
    with sim_cols_controls[1]:
        ss.similarity_top_k = st.number_input(
            "Number of results (Top K)",
            min_value=1,
            max_value=50,
            value=ss.similarity_top_k,
            step=1,
            key="similarity_top_k_input",
        )
    with sim_cols_controls[2]:
        ss.similarity_metric = st.selectbox(
            "Similarity Metric",
            options=["cosine", "l2"],
            index=["cosine", "l2"].index(ss.similarity_metric),
            key="similarity_metric_select",
        )

    if uploaded_file is not None:
        # Display uploaded image
        try:
            pil_image = Image.open(uploaded_file)
            # Resize for display if too large, maintaining aspect ratio
            pil_image.thumbnail((300, 300))
            st.image(
                pil_image, caption="Your Query Face", width=200
            )  # Display smaller version

            # Store b64 for potential re-display if results are cleared
            buffered_display = BytesIO()
            pil_image.save(buffered_display, format=pil_image.format or "PNG")
            ss.similarity_query_image_b64 = base64.b64encode(
                buffered_display.getvalue()
            ).decode()

        except UnidentifiedImageError:
            st.error("Could not read the uploaded image. Please try a different file.")
            uploaded_file = None  # Reset
            ss.similarity_query_image_b64 = None
        except Exception as e:
            st.error(f"Error processing uploaded image: {e}")
            uploaded_file = None
            ss.similarity_query_image_b64 = None

    if st.button(
        "🔍 Find Similar Faces",
        key="find_similar_btn",
        type="primary",
        disabled=uploaded_file is None,
    ):
        if uploaded_file:
            image_bytes = uploaded_file.getvalue()  # Get bytes from UploadedFile object
            filename = uploaded_file.name

            with st.spinner("Searching for similar faces... This might take a moment."):
                results = find_similar_faces(
                    event_code=ss.event_code,
                    image_file_bytes=image_bytes,
                    image_filename=filename,
                    metric=ss.similarity_metric,
                    top_k=ss.similarity_top_k,
                )
                if results:
                    st.success(f"Found {len(results)} similar faces.")
                    ss.similarity_results = results
                else:
                    st.info("No similar faces found matching the criteria.")
                    ss.similarity_results = []  # Empty list means search was successful but no results
        else:
            st.warning("Please upload an image first.")

    st.markdown("---")

    if ss.similarity_results is not None:
        if not ss.similarity_results:  # Empty list
            st.info(
                "No similar faces were found based on your query image and settings."
            )
        else:
            st.subheader(f"Top {len(ss.similarity_results)} Similar Faces Found:")

            # Prepare display data for similar faces
            similar_faces_display_data = []
            for result_face in ss.similarity_results:
                img_url = result_face.get("azure_blob_url")
                bbox = result_face.get("bbox")
                cluster_id_of_similar = result_face.get(
                    "cluster_id"
                )  # This is the cluster ID of the *found* similar face
                distance = result_face.get("distance", -1.0)

                cropped_face_b64 = None
                if img_url and bbox:
                    full_image_bytes = fetch_image_bytes_from_url(img_url)
                    if full_image_bytes:
                        cropped_face_b64 = crop_and_encode_face(
                            full_image_bytes, bbox, SIMILAR_FACE_DISPLAY_SIZE
                        )

                similar_faces_display_data.append(
                    {
                        "face_html": cropped_face_b64
                        if cropped_face_b64
                        else f"<div class='similar-face-placeholder'>Face (P ID: {cluster_id_of_similar})<br/>Dist: {distance:.3f}</div>",
                        "is_placeholder": not bool(cropped_face_b64),
                        "cluster_id": cluster_id_of_similar,
                        "distance": distance,
                        "image_uuid": result_face.get(
                            "image_uuid"
                        ),  # For potential future use
                    }
                )

            grid_cols_similar = st.columns(
                PERSON_CARD_COLS
            )  # Reuse same number of columns
            for i, face_data in enumerate(similar_faces_display_data):
                with grid_cols_similar[i % PERSON_CARD_COLS]:
                    # Each similar face card
                    st.markdown(
                        "<div class='similar-face-card'>", unsafe_allow_html=True
                    )
                    if face_data["is_placeholder"]:
                        st.markdown(face_data["face_html"], unsafe_allow_html=True)
                    else:
                        st.image(
                            face_data["face_html"], width=SIMILAR_FACE_DISPLAY_SIZE[0]
                        )

                    st.caption(
                        f"Person ID: {face_data['cluster_id']} (Dist: {face_data['distance']:.3f})"
                    )

                    # Button to view this person's images in gallery
                    btn_key = f"view_similar_person_{face_data['cluster_id']}_{i}"
                    if face_data["cluster_id"] not in [
                        CLUSTER_ID_UNASSIGNED,
                        CLUSTER_ID_PROCESSING,
                    ]:  # Only allow filtering for valid clusters
                        if st.button(
                            "View This Person's Images",
                            key=btn_key,
                            type="secondary",
                            use_container_width=True,
                        ):
                            ss.gallery_filter_cluster_list = [
                                face_data["cluster_id"]
                            ]  # Filter by this single cluster
                            ss.gallery_page = 1
                            ss.gallery_date_from = None
                            ss.gallery_date_to = None
                            ss.gallery_min_faces = 0
                            ss.gallery_max_faces = 0
                            st.switch_page(
                                "pages/02_Gallery.py"
                            )  # Ensure correct gallery page name
                    st.markdown("</div>", unsafe_allow_html=True)
    elif ss.similarity_query_image_b64:  # If query image was uploaded but no results yet (e.g. before search or after error)
        st.markdown("##### Your Query Image:")
        st.image(f"data:image/png;base64,{ss.similarity_query_image_b64}", width=150)


# --- Custom CSS (Consolidated from previous Identical People tab) ---
st.markdown(
    f"""
<style>
    /* Styles for Identified People Tab */
    .person-card-visuals {{
        display: flex; flex-direction: column; align-items: center;
        text-align: center; margin-bottom: 10px; 
    }}
    .person-face-circle {{
        width: {SAMPLE_FACE_DISPLAY_SIZE[0]}px; height: {SAMPLE_FACE_DISPLAY_SIZE[1]}px;
        border-radius: 50%; object-fit: cover; margin-bottom: 10px;
        background-color: #e0e0e0;
        transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
    }}
    .person-face-circle:hover {{
        transform: scale(1.05); box-shadow: 0px 4px 12px rgba(0,0,0,0.15);
    }}
    .person-label {{
        font-weight: bold; font-size: 0.9em; margin-bottom: 0px; color: #333;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;
    }}

    /* Common styles for column wrappers if needed */
    /* div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"] {{ ... }} */
    
    /* Checkbox alignment for Identified People Tab */
    div[data-testid="stCheckbox"] {{ /* This is general, might need more specificity if it conflicts */
        display: flex; justify-content: center; padding-top: 5px; padding-bottom: 5px;   
    }}

    /* Styles for Unassigned/Processing expander images */
    div[data-testid="stExpander"] div[data-testid="stImage"] img {{
        border-radius: 50%; object-fit: cover; border: 2px solid #ddd;
    }}

    /* Styles for Similarity Search Tab Results */
    .similar-face-card {{
        display: flex;
        flex-direction: column;
        align-items: center; /* Center image and caption */
        text-align: center;
        padding: 8px;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-bottom: 15px;
        background-color: #f9f9f9;
    }}
    .similar-face-card img {{ /* Targets images rendered by st.image from b64 string */
        border-radius: 50%; /* Make displayed similar faces circular */
        margin-bottom: 8px;
    }}
    .similar-face-placeholder {{
        width: {SIMILAR_FACE_DISPLAY_SIZE[0]}px; height: {SIMILAR_FACE_DISPLAY_SIZE[1]}px;
        border-radius: 50%; background-color: #e0e0e0; display: flex;
        justify-content: center; align-items: center; font-size: 0.8em;
        color: #555; border: 1px solid #ccc; margin-bottom: 8px;
        padding: 5px; box-sizing: border-box;
    }}
    .similar-face-card div[data-testid="stCaption"] {{ /* Targets st.caption under similar faces */
        font-size: 0.8em;
        color: #333;
        margin-bottom: 8px;
    }}
    .similar-face-card div[data-testid="stButton"] > button {{ /* Targets button under similar faces */
        font-size: 0.85em;
        padding: 4px 8px;
    }}

</style>
""",
    unsafe_allow_html=True,
)
