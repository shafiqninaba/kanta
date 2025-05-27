import zipfile
from datetime import datetime
from io import BytesIO

import streamlit as st

# Assuming your utils file is in utils/image_helpers.py
from utils.api import get_image_detail, get_images
from utils.image_helpers import crop_and_encode_face, fetch_image_bytes_from_url
from utils.session import get_event_selection, init_session_state

# --- Page Configuration ---
st.set_page_config(page_title="Image Gallery", page_icon="🖼️", layout="wide")

# --- Initialize Session State & Event Selection ---
init_session_state()
get_event_selection()

# --- Constants ---
IMAGES_PER_PAGE_OPTIONS = [10, 20, 30, 50, 100]
DEFAULT_IMAGES_PER_PAGE = 20
NUM_IMAGE_GRID_COLS = 5
THUMBNAIL_ASPECT_RATIO_PADDING = "100%"
CLUSTER_ID_UNASSIGNED = -1
CLUSTER_ID_PROCESSING = -2

# --- Session State for this page ---
ss = st.session_state
ss.setdefault("gallery_date_from", None)
ss.setdefault("gallery_date_to", None)
ss.setdefault("gallery_min_faces", 0)
ss.setdefault("gallery_max_faces", 0)
ss.setdefault("gallery_limit", DEFAULT_IMAGES_PER_PAGE)
ss.setdefault("gallery_page", 1)
ss.setdefault("gallery_selected_images", {})  # uuid: azure_blob_url for bulk download
ss.setdefault("gallery_prepare_download_flag", False)
ss.setdefault("gallery_download_ready_data", None)
ss.setdefault("gallery_download_ready_filename", None)
ss.setdefault("gallery_download_ready_mimetype", None)
ss.setdefault(
    "gallery_filter_cluster_list", None
)  # Stores list of cluster_ids for main gallery filter
# New: {image_uuid: {face_idx_in_image: {"selected": bool, "cluster_id": int}}}
ss.setdefault("gallery_popover_selected_faces_detail", {})


# --- Main Application ---
st.title("Image Gallery")

active_cluster_filter = ss.get("gallery_filter_cluster_list")
filter_cols_upper_row = st.columns([6, 1.5])

with filter_cols_upper_row[0]:
    if (
        active_cluster_filter
        and isinstance(active_cluster_filter, list)
        and len(active_cluster_filter) > 0
    ):
        cluster_ids_str = ", ".join(map(str, sorted(list(set(active_cluster_filter)))))
        st.info(
            f"ℹ️ Displaying images for selected people (Person IDs: {cluster_ids_str})."
        )
    # No "else" here, the main markdown welcome message is below if no filter

if not ss.get("event_code"):
    st.warning("👈 Please select an event from the sidebar to view images.")
    st.stop()

# --- Filter Bar ---
st.markdown("#### Filter Images")
filter_cols = st.columns(
    [
        1.5,
        1.5,
        1,
        1,
        1,
        1,
        1,
        1.5,
    ]  # Increased from 0.7 to 1 for the number inputs/selectbox
)

with filter_cols[0]:
    date_from = st.date_input("From", ss.gallery_date_from, key="gallery_filter_df")
with filter_cols[1]:
    date_to = st.date_input("To", ss.gallery_date_to, key="gallery_filter_dt")
with filter_cols[2]:
    min_faces = st.number_input(
        "Min",
        0,
        value=ss.gallery_min_faces,
        key="gallery_filter_mf",
        step=1,
        help="Min faces",
    )
with filter_cols[3]:
    max_faces = st.number_input(
        "Max",
        0,
        value=ss.gallery_max_faces,
        key="gallery_filter_maf",
        step=1,
        help="Max faces",
    )
with filter_cols[4]:
    limit = st.selectbox(
        "Limit",
        IMAGES_PER_PAGE_OPTIONS,
        index=IMAGES_PER_PAGE_OPTIONS.index(ss.gallery_limit),
        key="gallery_filter_l",
        help="Images per page",
    )
with filter_cols[5]:
    page = st.number_input(
        "Page", 1, value=ss.gallery_page, key="gallery_filter_p", step=1
    )

with filter_cols[6]:
    st.write("")
    st.write("")
    if (
        active_cluster_filter
        and isinstance(active_cluster_filter, list)
        and len(active_cluster_filter) > 0
    ):
        if st.button(
            "Clear People Filter",
            key="clear_gallery_cluster_filter_main",
            help="Remove the filter based on people selected from the 'People' page or popovers.",
            use_container_width=True,
        ):
            ss.gallery_filter_cluster_list = None
            ss.gallery_page = 1
            ss.gallery_popover_selected_faces_detail = {}  # Clear popover states
            st.rerun()
    else:
        st.markdown("<div style='height: 38px;'></div>", unsafe_allow_html=True)

filters_changed_by_user_main = False
if date_from != ss.gallery_date_from:
    ss.gallery_date_from = date_from
    filters_changed_by_user_main = True
if date_to != ss.gallery_date_to:
    ss.gallery_date_to = date_to
    filters_changed_by_user_main = True
if min_faces != ss.gallery_min_faces:
    ss.gallery_min_faces = min_faces
    filters_changed_by_user_main = True
if max_faces != ss.gallery_max_faces:
    ss.gallery_max_faces = max_faces
    filters_changed_by_user_main = True
if limit != ss.gallery_limit:
    ss.gallery_limit = limit
if page != ss.gallery_page:
    ss.gallery_page = page

if filters_changed_by_user_main and ss.get("gallery_filter_cluster_list") is not None:
    ss.gallery_filter_cluster_list = None
    ss.gallery_popover_selected_faces_detail = {}
    ss.gallery_page = 1

api_filter_params = {
    "date_from": f"{date_from}T00:00:00" if date_from else None,
    "date_to": f"{date_to}T23:59:59" if date_to else None,
    "min_faces": min_faces if min_faces > 0 else None,
    "max_faces": max_faces if max_faces > 0 else None,
    "limit": limit,
    "offset": (page - 1) * limit,
    "cluster_list_id": ss.get("gallery_filter_cluster_list"),
}

with filter_cols[7]:  # Download button logic
    st.write("")
    st.write("")
    num_selected_for_download_display = len(ss.gallery_selected_images)
    if st.button(
        "Download Selected",
        key="gallery_btn_prep_download",
        type="primary" if num_selected_for_download_display > 0 else "secondary",
        disabled=num_selected_for_download_display == 0,
        use_container_width=True,
    ):
        if len(ss.gallery_selected_images) > 0:
            ss.gallery_prepare_download_flag = True
            ss.gallery_download_ready_data = None
        else:
            st.warning("No images selected.")
            ss.gallery_prepare_download_flag = False
        st.rerun()
    if ss.get("gallery_prepare_download_flag", False):
        num_preparing = len(ss.gallery_selected_images)
        if num_preparing == 0:
            ss.gallery_prepare_download_flag = False
        else:
            with st.spinner(f"Preparing {num_preparing} image(s)..."):
                if num_preparing == 1:
                    uuid, url = list(ss.gallery_selected_images.items())[0]
                    img_bytes = fetch_image_bytes_from_url(url)
                    if img_bytes:
                        ext = (
                            url.split(".")[-1].lower()
                            if "." in url.split("/")[-1]
                            else "jpg"
                        )
                        ext = ext if len(ext) <= 4 and ext.isalnum() else "jpg"
                        (
                            ss.gallery_download_ready_data,
                            ss.gallery_download_ready_filename,
                            ss.gallery_download_ready_mimetype,
                        ) = img_bytes, f"{ss.event_code}_{uuid}.{ext}", f"image/{ext}"
                    else:
                        st.error(f"Failed to fetch image {uuid[:8]}.")
                else:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for uuid, url in ss.gallery_selected_images.items():
                            img_bytes = fetch_image_bytes_from_url(url)
                            if img_bytes:
                                ext = (
                                    url.split(".")[-1].lower()
                                    if "." in url.split("/")[-1]
                                    else "jpg"
                                )
                                ext = ext if len(ext) <= 4 and ext.isalnum() else "jpg"
                                zf.writestr(
                                    f"{ss.event_code}_{uuid}.{ext}",
                                    img_bytes.getvalue(),
                                )
                    zip_buffer.seek(0)
                    (
                        ss.gallery_download_ready_data,
                        ss.gallery_download_ready_filename,
                        ss.gallery_download_ready_mimetype,
                    ) = zip_buffer, f"{ss.event_code}_selected.zip", "application/zip"
            if ss.gallery_download_ready_data:
                st.toast("Download ready!", icon="✅")
            ss.gallery_prepare_download_flag = False
            st.rerun()
    if ss.get("gallery_download_ready_data"):
        st.download_button(
            label=f"Download: {ss.gallery_download_ready_filename}",
            data=ss.gallery_download_ready_data,
            file_name=ss.gallery_download_ready_filename,
            mime=ss.gallery_download_ready_mimetype,
            use_container_width=True,
            type="primary",
            on_click=lambda: ss.update(gallery_download_ready_data=None),
        )
st.markdown("---")


# --- Image Detail Popover Content Function (REVISED - STRICTLY NO st.columns for face items) ---
def image_detail_popover_content_fn(image_uuid_for_popover: str):
    details_data, success = get_image_detail(image_uuid_for_popover)
    if not success or not details_data:
        st.error(f"Details unavailable: {details_data}")
        return
    image_info = details_data.get("image", {})
    faces_info = details_data.get("faces", [])
    if not image_info:
        st.warning("Image metadata missing.")
        return

    st.image(image_info.get("azure_blob_url"), use_container_width=True)
    upload_time_str = image_info.get("created_at")
    if upload_time_str:
        try:
            st.caption(
                f"Uploaded: {datetime.fromisoformat(str(upload_time_str).replace('Z', '+00:00')).strftime('%b %d, %Y %H:%M')}"
            )
        except:
            st.caption(f"Uploaded: {upload_time_str}")
    st.caption(
        f"Faces: {len(faces_info)} | Type: {image_info.get('file_extension','N/A').upper()}"
    )

    if faces_info:
        st.markdown("###### Select Individual Faces to Filter By:")

        if image_uuid_for_popover not in ss.gallery_popover_selected_faces_detail:
            ss.gallery_popover_selected_faces_detail[image_uuid_for_popover] = {}
        popover_face_map = ss.gallery_popover_selected_faces_detail[
            image_uuid_for_popover
        ]

        original_image_bytes_io = fetch_image_bytes_from_url(
            image_info.get("azure_blob_url")
        )

        if original_image_bytes_io:
            processed_faces_count = 0
            for face_idx, face_meta in enumerate(faces_info):
                # --- Each face item will be a vertical stack ---

                bbox = face_meta.get("bbox")
                cluster_id = face_meta.get("cluster_id")
                face_uuid = face_meta.get("uuid", f"face_{face_idx}")

                if face_idx not in popover_face_map:
                    popover_face_map[face_idx] = {
                        "selected": False,
                        "cluster_id": cluster_id,
                        "face_uuid": face_uuid,
                    }

                # 1. Display Face Image (centered)
                b64_img_html = ""
                if isinstance(bbox, dict) and all(
                    k in bbox for k in ["x", "y", "width", "height"]
                ):
                    fresh_bytes_io = BytesIO(original_image_bytes_io.getvalue())
                    b64_img = crop_and_encode_face(
                        fresh_bytes_io, bbox, (60, 60), 0.15, 0.15
                    )
                    if b64_img:
                        st.markdown(
                            f"<div class='popover-face-image-wrapper'><img src='{b64_img}' class='face-img-popover-selectable' alt='Face'></div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div class='popover-face-image-wrapper'><div class='face-img-popover-placeholder'>Face</div></div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        "<div class='popover-face-image-wrapper'><div class='face-img-popover-placeholder'>Face</div></div>",
                        unsafe_allow_html=True,
                    )

                # 2. Display Checkbox OR Special Indicator (below the image)
                is_special_cluster = cluster_id in [
                    CLUSTER_ID_UNASSIGNED,
                    CLUSTER_ID_PROCESSING,
                ]

                if is_special_cluster:
                    status_text = (
                        "Unidentified"
                        if cluster_id == CLUSTER_ID_UNASSIGNED
                        else "Processing"
                    )
                    icon = "❌" if cluster_id == CLUSTER_ID_UNASSIGNED else "⏳"
                    st.markdown(  # This will render below the image
                        f"""
                        <div class="special-face-indicator-stacked" title="This face is {status_text.lower()} and cannot be selected for filtering.">
                            <span class="indicator-icon">{icon}</span>
                            <span class="indicator-text-small">{status_text}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    popover_face_map[face_idx]["selected"] = False
                else:
                    chk_key = f"popover_select_{image_uuid_for_popover}_{face_uuid}_{face_idx}"
                    is_currently_selected = popover_face_map[face_idx]["selected"]
                    # Checkbox will render below the image
                    new_selection_state = st.checkbox(
                        f"Person {cluster_id if cluster_id is not None else 'N/A'}",
                        value=is_currently_selected,
                        key=chk_key,
                        help=f"Select to filter by Person ID: {cluster_id}"
                        if cluster_id is not None
                        else "Select this face",
                    )
                    popover_face_map[face_idx]["selected"] = new_selection_state

                processed_faces_count += 1
                if face_idx < len(faces_info) - 1:
                    st.markdown("---")  # Divider between face entries

            if processed_faces_count == 0 and len(faces_info) > 0:
                st.caption("No faces available for selection in this image.")

            # --- Filter button logic (remains the same) ---
            valid_selected_cluster_ids_in_popover = []
            for face_idx_data in popover_face_map.values():
                if face_idx_data["selected"] and face_idx_data["cluster_id"] not in [
                    CLUSTER_ID_UNASSIGNED,
                    CLUSTER_ID_PROCESSING,
                ]:
                    valid_selected_cluster_ids_in_popover.append(
                        face_idx_data["cluster_id"]
                    )
            valid_selected_cluster_ids_in_popover = sorted(
                list(set(valid_selected_cluster_ids_in_popover))
            )

            if st.button(
                f"Filter by these {len(valid_selected_cluster_ids_in_popover)} Person(s)",
                key=f"filter_btn_popover_{image_uuid_for_popover}",
                type="primary",
                disabled=not valid_selected_cluster_ids_in_popover,
                use_container_width=True,
            ):
                ss.gallery_filter_cluster_list = valid_selected_cluster_ids_in_popover
                ss.gallery_page = 1
                ss.gallery_date_from, ss.gallery_date_to = None, None
                ss.gallery_min_faces, ss.gallery_max_faces = 0, 0
                st.rerun()
        else:
            st.caption("Original image data unavailable for face display.")
    else:
        st.caption("No faces detected in this image.")


# --- Fetch and Display Images in Grid ---
if ss.event_code:
    image_display_placeholder = st.empty()
    image_display_placeholder.info("⏳ Loading images...")

    cluster_filter_for_api = api_filter_params.get("cluster_list_id")
    if cluster_filter_for_api is not None and not (
        isinstance(cluster_filter_for_api, list)
        and all(isinstance(item, int) for item in cluster_filter_for_api)
    ):
        api_filter_params["cluster_list_id"] = None

    images_response_data, success = get_images(ss.event_code, **api_filter_params)

    if success:
        if not isinstance(images_response_data, list):
            image_display_placeholder.error(
                f"API Error: Expected list, got {type(images_response_data)}"
            )
            st.stop()
        fetched_images_list = images_response_data
        image_display_placeholder.empty()
        if not fetched_images_list:
            msg = (
                "No images found for the selected people and other active filters."
                if ss.get("gallery_filter_cluster_list")
                else "No images found for the current filters."
            )
            st.info(msg)
        else:
            st.write(f"Displaying {len(fetched_images_list)} image(s).")
            grid_cols = st.columns(NUM_IMAGE_GRID_COLS)
            for i, img_meta in enumerate(fetched_images_list):
                with grid_cols[i % NUM_IMAGE_GRID_COLS]:
                    with st.container():
                        st.markdown(
                            f"""<div class="image-grid-cell" title="Faces: {img_meta['faces']}"> 
                                        <img src="{img_meta['azure_blob_url']}" class="grid-thumbnail-image" alt="Image {img_meta['uuid'][:8]}">
                                    </div>""",
                            unsafe_allow_html=True,
                        )
                        controls_cols = st.columns([0.7, 0.3])
                        with controls_cols[0]:
                            with st.popover(
                                "View Photo",
                                use_container_width=True,
                                help=f"View full photo and details for {img_meta['uuid'][:8]}",
                            ):
                                image_detail_popover_content_fn(img_meta["uuid"])
                        with controls_cols[1]:
                            is_selected_download = st.checkbox(
                                "",
                                value=(img_meta["uuid"] in ss.gallery_selected_images),
                                key=f"gallery_select_img_{img_meta['uuid']}",
                                label_visibility="collapsed",
                                help="Select for download",
                            )
                            if is_selected_download:
                                ss.gallery_selected_images[img_meta["uuid"]] = img_meta[
                                    "azure_blob_url"
                                ]
                            elif img_meta["uuid"] in ss.gallery_selected_images:
                                del ss.gallery_selected_images[img_meta["uuid"]]
    else:
        image_display_placeholder.error(
            f"Failed to load images: {images_response_data}"
        )

# --- Custom CSS ---
st.markdown(
    f"""
<style>
    /* --- Main Image Gallery Grid (Outside Popover) --- */
    .image-grid-cell {{
        width: 100%;
        padding-top: {THUMBNAIL_ASPECT_RATIO_PADDING}; /* Python variable */
        position: relative; 
        border-radius: 6px;
        margin-bottom: 5px;
        background-color: #f0f2f6; 
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        overflow: hidden; 
    }}
    .grid-thumbnail-image {{
        position: absolute; 
        top: 0; left: 0; 
        width: 100%; height: 100%; 
        object-fit: contain; 
        object-position: center; 
    }}

    /* --- Popover Trigger Button ("View Photo") --- */
    div[data-testid="stPopover"] > button {{
        font-size: 0.8rem; 
        padding: 3px 8px; 
        border: 1px solid #d1d1d1; 
        background-color: #f8f9fa; 
        color: #212529;
        width: 100%; 
        text-align: center; 
        margin-top: 2px;
    }}
    div[data-testid="stPopover"] > button:hover {{
        background-color: #e9ecef; 
        border-color: #adb5bd;
    }}

    /* --- General Checkbox Styling (for download selection on main gallery items) --- */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stVerticalBlock"] > div[data-testid="stCheckbox"] {{ 
        display: flex; 
        justify-content: center; 
        align-items: center;
        height: 100%; 
        padding-top: 3px; 
        margin-top: 2px; 
    }}
    
    /* --- Popover Content: Face Selection (Vertical Stack) --- */

    /* Wrapper for each face image to allow centering */
    .popover-face-image-wrapper {{
        display: flex;
        justify-content: center; /* Center the image horizontally */
        margin-bottom: 5px;    /* Space below image before checkbox/indicator */
    }}
    .face-img-popover-selectable {{ 
        width: 60px; 
        height: 60px;
        border-radius: 50%; 
        object-fit: cover;
        border: 1px solid #ccc; 
    }}
    .face-img-popover-placeholder {{ 
        width: 60px; height: 60px; border-radius: 50%; background-color: #e0e0e0; 
        display: flex; justify-content: center; align-items: center; 
        font-size: 0.8em; color: #555; border: 1px solid #ccc;
    }}

    /* Special Indicator for Non-Selectable Faces (stacked below image) */
    .special-face-indicator-stacked {{ 
        display: flex;
        flex-direction: row; 
        align-items: center;
        justify-content: center; /* Center content of the indicator */
        width: fit-content; /* Adjust width to content */
        margin: 0 auto 5px auto; /* Center the block and add bottom margin */
        padding: 4px 8px; 
        color: #6c757d; 
        border-radius: 0.25rem;
        font-size: 0.85em; 
        opacity: 0.8; 
        cursor: not-allowed; 
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        min-height: 30px; 
        box-sizing: border-box;
    }}
    .special-face-indicator-stacked .indicator-icon {{
        margin-right: 0.5em;
        font-size: 1.1em; 
    }}

    /* Streamlit Checkbox within Popover (stacked below image) */
    div[data-testid="stPopover"] div[data-testid="stCheckbox"] {{
        width: 100% !important; /* Checkbox takes available width for its label */
        margin: 0 0 5px 0 !important; /* No horizontal auto margin, bottom margin for spacing */
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important; /* Align checkbox and label to the left */
    }}
    div[data-testid="stPopover"] div[data-testid="stCheckbox"] label {{
        font-size: 0.85em;
        padding-left: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        /* max-width: 180px; /* Adjust if needed */
    }}
    div[data-testid="stPopover"] div[data-testid="stCheckbox"] input[type="checkbox"] {{
        transform: scale(0.9);
        margin-right: 0px; 
    }}
    
    /* Horizontal Rule (---) styling within popover */
    div[data-testid="stPopover"] div[data-testid="stHorizontalRule"] {{
        margin-top: 10px;
        margin-bottom: 10px;
        border-top-width: 1px;
    }}

    /* Filter Button at the bottom of the popover */
    div[data-testid="stPopover"] div[data-testid="stButton"] > button[kind="primary"] {{
        margin-top: 15px; 
    }}

</style>
""",
    unsafe_allow_html=True,
)
