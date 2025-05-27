import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
import requests
from io import BytesIO
from datetime import datetime
import base64
import zipfile
from typing import List, Optional  # For type hinting

from utils.api import (
    get_images,
    get_image_detail,
)  # get_images now takes cluster_list_id
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
# TINT_BLACK_SEPIA = "#704214" # Not used in current code
# TINT_WHITE_SEPIA = "#C0A080" # Not used in current code

# --- Session State for this page ---
ss = st.session_state
ss.setdefault("gallery_date_from", None)
ss.setdefault("gallery_date_to", None)
ss.setdefault("gallery_min_faces", 0)
ss.setdefault("gallery_max_faces", 0)
ss.setdefault("gallery_limit", DEFAULT_IMAGES_PER_PAGE)
ss.setdefault("gallery_page", 1)
ss.setdefault("gallery_selected_images", {})  # uuid: azure_blob_url
ss.setdefault("gallery_prepare_download_flag", False)
ss.setdefault("gallery_download_ready_data", None)
ss.setdefault("gallery_download_ready_filename", None)
ss.setdefault("gallery_download_ready_mimetype", None)
ss.setdefault(
    "gallery_filter_cluster_list", None
)  # NEW: To store cluster IDs from People page


# --- Helper Function to fetch image bytes ---
@st.cache_data(ttl=3600)
def fetch_image_bytes_from_url(image_url: str) -> BytesIO | None:
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        return BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching image data from {image_url[:60]}...: {e}")
        return None


# --- Main Application ---
st.title("Image Gallery")

# Display active cluster filter if any
active_cluster_filter = ss.get("gallery_filter_cluster_list")
if (
    active_cluster_filter
    and isinstance(active_cluster_filter, list)
    and len(active_cluster_filter) > 0
):
    cluster_ids_str = ", ".join(map(str, active_cluster_filter))
    st.info(
        f"ℹ️ Showing images for selected people (Person IDs: {cluster_ids_str}). "
        "Clear selection from 'People' page or use filters below to change view."
    )
    # Add a button to clear this specific filter directly from the gallery
    if st.button("Clear People Filter", key="clear_gallery_cluster_filter"):
        ss.gallery_filter_cluster_list = None
        ss.gallery_page = 1  # Reset page
        st.rerun()
else:
    st.markdown(
        "Welcome to the Image Gallery! Explore images from your selected event. "
        "Use the filters below to refine your search, and click 'View Photo' for a closer look."
    )


if not ss.get("event_code"):
    st.warning("👈 Please select an event from the sidebar to view images.")
    st.stop()

# --- Filter Bar ---
st.markdown("#### Filter Images")
filter_cols = st.columns([1.5, 1.5, 0.8, 0.8, 0.8, 0.8, 1.5])

with filter_cols[0]:
    date_from = st.date_input("From", ss.gallery_date_from, key="gallery_filter_df")
with filter_cols[1]:
    date_to = st.date_input("To", ss.gallery_date_to, key="gallery_filter_dt")
with filter_cols[2]:
    min_faces = st.number_input(
        "Min Faces", 0, value=ss.gallery_min_faces, key="gallery_filter_mf", step=1
    )
with filter_cols[3]:
    max_faces = st.number_input(
        "Max Faces", 0, value=ss.gallery_max_faces, key="gallery_filter_maf", step=1
    )
with filter_cols[4]:
    limit = st.selectbox(
        "Per Page",
        IMAGES_PER_PAGE_OPTIONS,
        index=IMAGES_PER_PAGE_OPTIONS.index(ss.gallery_limit),
        key="gallery_filter_l",
    )
with filter_cols[5]:
    page = st.number_input(
        "Page", 1, value=ss.gallery_page, key="gallery_filter_p", step=1
    )

# Update session state
# If any of these filters are changed by the user, it implies they want to override the cluster filter from People.py
# Or, we can decide that these filters apply *in addition* to the cluster filter.
# For now, let's assume changing any of these main filters *clears* the specific cluster_list filter from People.py
# to avoid confusion, unless explicitly stated otherwise.
# However, a more advanced UX might keep them additive.

filters_changed_by_user = False
if date_from != ss.gallery_date_from:
    ss.gallery_date_from = date_from
    filters_changed_by_user = True
if date_to != ss.gallery_date_to:
    ss.gallery_date_to = date_to
    filters_changed_by_user = True
if min_faces != ss.gallery_min_faces:
    ss.gallery_min_faces = min_faces
    filters_changed_by_user = True
if max_faces != ss.gallery_max_faces:
    ss.gallery_max_faces = max_faces
    filters_changed_by_user = True
if limit != ss.gallery_limit:
    ss.gallery_limit = limit
    # Changing limit typically doesn't imply clearing other conceptual filters
if page != ss.gallery_page:
    ss.gallery_page = page
    # Changing page also doesn't imply clearing other conceptual filters

# If user changes date/face filters, clear the specific cluster_list from People page
# This makes the People page filter a "one-shot" entry point for those clusters.
if filters_changed_by_user and ss.get("gallery_filter_cluster_list") is not None:
    # st.toast("Cluster filter cleared due to change in other filters.", icon="⚠️") # Optional feedback
    ss.gallery_filter_cluster_list = None
    ss.gallery_page = 1  # Reset page if filters change significantly

api_filter_params = {
    "date_from": f"{date_from}T00:00:00" if date_from else None,
    "date_to": f"{date_to}T23:59:59" if date_to else None,
    "min_faces": min_faces if min_faces > 0 else None,
    "max_faces": max_faces if max_faces > 0 else None,
    "limit": limit,
    "offset": (page - 1) * limit,
    "cluster_list_id": ss.get(
        "gallery_filter_cluster_list"
    ),  # Pass the list from session state
}

# --- Download Button Area (remains largely the same) ---
with filter_cols[6]:
    st.write("")
    st.write("")
    num_selected_for_download_display = len(ss.gallery_selected_images)
    if st.button(
        "Download Selected",
        key="gallery_btn_prep_download",
        type="primary" if num_selected_for_download_display > 0 else "secondary",
        disabled=num_selected_for_download_display == 0,
        use_container_width=True,
        help="Prepare selected images for download.",
    ):
        num_to_prepare_on_click = len(ss.gallery_selected_images)
        if num_to_prepare_on_click > 0:
            ss.gallery_prepare_download_flag = True
            ss.gallery_download_ready_data = None
        else:
            st.warning("No images selected to download.")
            ss.gallery_prepare_download_flag = False
        st.rerun()

    if ss.get("gallery_prepare_download_flag", False):
        num_actually_preparing = len(ss.gallery_selected_images)
        if num_actually_preparing == 0:
            ss.gallery_prepare_download_flag = False
        else:
            with st.spinner(
                f"Preparing {num_actually_preparing} image(s)... Please wait."
            ):
                if num_actually_preparing == 1:
                    uuid, url = list(ss.gallery_selected_images.items())[0]
                    image_bytes_io = fetch_image_bytes_from_url(url)
                    if image_bytes_io:
                        ext = (
                            url.split(".")[-1].lower()
                            if "." in url.split("/")[-1]
                            else "jpg"
                        )
                        ext = ext if len(ext) <= 4 and ext.isalnum() else "jpg"
                        ss.gallery_download_ready_data = image_bytes_io
                        ss.gallery_download_ready_filename = (
                            f"{ss.event_code}_{uuid}.{ext}"
                        )
                        ss.gallery_download_ready_mimetype = f"image/{ext}"
                    else:
                        st.error(f"Could not fetch image {uuid[:8]}.")
                elif num_actually_preparing > 1:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                        for i, (uuid, url) in enumerate(
                            ss.gallery_selected_images.items()
                        ):
                            image_bytes_io = fetch_image_bytes_from_url(url)
                            if image_bytes_io:
                                ext = (
                                    url.split(".")[-1].lower()
                                    if "." in url.split("/")[-1]
                                    else "jpg"
                                )
                                ext = ext if len(ext) <= 4 and ext.isalnum() else "jpg"
                                zf.writestr(
                                    f"{ss.event_code}_{uuid}.{ext}",
                                    image_bytes_io.getvalue(),
                                )
                    zip_buffer.seek(0)
                    ss.gallery_download_ready_data = zip_buffer
                    ss.gallery_download_ready_filename = (
                        f"{ss.event_code}_selected_images.zip"
                    )
                    ss.gallery_download_ready_mimetype = "application/zip"
            if ss.gallery_download_ready_data:
                st.toast("Download is ready below!", icon="✅")
            ss.gallery_prepare_download_flag = False
            st.rerun()

    if ss.get("gallery_download_ready_data"):
        st.download_button(
            label=f"Click to Download: {ss.gallery_download_ready_filename}",
            data=ss.gallery_download_ready_data,
            file_name=ss.gallery_download_ready_filename,
            mime=ss.gallery_download_ready_mimetype,
            key="gallery_final_download_action_button",
            use_container_width=True,
            type="primary",
            on_click=lambda: ss.update(
                gallery_download_ready_data=None,
                gallery_download_ready_filename=None,
                gallery_download_ready_mimetype=None,
            ),
        )
st.markdown("---")


# --- Image Detail Popover Content Function (remains the same) ---
def image_detail_popover_content_fn(image_uuid_for_popover: str):
    # ... (content from your provided Gallery.py, no changes needed here) ...
    details_data, success = get_image_detail(image_uuid_for_popover)
    if not success:
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
            upload_dt = datetime.fromisoformat(
                str(upload_time_str).replace("Z", "+00:00")
            )
            st.caption(f"Uploaded: {upload_dt.strftime('%b %d, %Y %H:%M')}")
        except:
            st.caption(f"Uploaded: {upload_time_str}")
    st.caption(
        f"Faces: {len(faces_info)} | Type: {image_info.get('file_extension','N/A').upper()}"
    )
    if faces_info:
        st.markdown("###### Detected Faces")
        original_image_bytes_io = fetch_image_bytes_from_url(
            image_info.get("azure_blob_url")
        )
        if original_image_bytes_io:
            try:
                pil_original_image = Image.open(original_image_bytes_io)
                faces_html_parts = []
                for face_meta in faces_info:
                    bbox = face_meta.get("bbox")
                    if isinstance(bbox, dict) and all(
                        k in bbox for k in ["x", "y", "width", "height"]
                    ):
                        try:
                            x, y, w, h = (
                                int(bbox["x"]),
                                int(bbox["y"]),
                                int(bbox["width"]),
                                int(bbox["height"]),
                            )
                            pad_w, pad_h = (int(w * 0.25), int(h * 0.25))
                            crop_box = (
                                max(0, x - pad_w),
                                max(0, y - pad_h),
                                min(pil_original_image.width, x + w + pad_w),
                                min(pil_original_image.height, y + h + pad_h),
                            )
                            cropped_face_pil = pil_original_image.crop(crop_box)
                            if (
                                cropped_face_pil.width == 0
                                or cropped_face_pil.height == 0
                            ):
                                continue
                            cropped_face_bytes = BytesIO()
                            cropped_face_pil.save(cropped_face_bytes, "PNG")
                            cropped_face_bytes.seek(0)
                            b64_img = base64.b64encode(
                                cropped_face_bytes.getvalue()
                            ).decode("utf-8")
                            faces_html_parts.append(
                                f"<div class='face-crop-popover-item'><img src='data:image/png;base64,{b64_img}' class='face-img-popover' alt='Detected Face'></div>"
                            )
                        except Exception:
                            pass
                if faces_html_parts:
                    st.markdown(
                        f"<div class='faces-flex-container-popover'>{''.join(faces_html_parts)}</div>",
                        unsafe_allow_html=True,
                    )
                elif len(faces_info) > 0:
                    st.caption("Could not display face previews.")
            except Exception:
                st.caption("Note: Error preparing face display.")
        else:
            st.caption("Note: Original image data unavailable for face display.")


# --- Fetch and Display Images in Grid (remains largely the same, uses updated api_filter_params) ---
if ss.event_code:
    image_display_placeholder = st.empty()
    image_display_placeholder.info("⏳ Loading images...")

    # Ensure cluster_list_id is either a list of ints or None
    cluster_filter_for_api = api_filter_params.get("cluster_list_id")
    if cluster_filter_for_api is not None and not (
        isinstance(cluster_filter_for_api, list)
        and all(isinstance(item, int) for item in cluster_filter_for_api)
    ):
        # This case should not happen if People.py sends correct data, but good for safety
        # st.warning("Invalid cluster filter format; ignoring cluster filter.")
        api_filter_params["cluster_list_id"] = None  # Fallback to no cluster filter

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
            st.info("No images found for the current filters.")
        else:
            st.write(f"Displaying {len(fetched_images_list)} image(s).")
            grid_cols = st.columns(NUM_IMAGE_GRID_COLS)
            for i, img_meta in enumerate(fetched_images_list):
                with grid_cols[i % NUM_IMAGE_GRID_COLS]:
                    with st.container():
                        image_html_container = f"""
                        <div class="image-grid-cell" title="Faces: {img_meta['faces']}"> 
                             <img src="{img_meta['azure_blob_url']}" class="grid-thumbnail-image" alt="Image {img_meta['uuid'][:8]}">
                        </div>"""
                        st.markdown(image_html_container, unsafe_allow_html=True)
                        controls_cols = st.columns([0.7, 0.3])
                        with controls_cols[0]:
                            with st.popover(
                                "View Photo",
                                use_container_width=True,
                                help=f"View full photo and details for {img_meta['uuid'][:8]}",
                            ):
                                image_detail_popover_content_fn(img_meta["uuid"])
                        with controls_cols[1]:
                            is_selected = st.checkbox(
                                "",
                                value=(img_meta["uuid"] in ss.gallery_selected_images),
                                key=f"gallery_select_img_{img_meta['uuid']}",
                                label_visibility="collapsed",
                                help="Select for download",
                            )
                            if is_selected:
                                ss.gallery_selected_images[img_meta["uuid"]] = img_meta[
                                    "azure_blob_url"
                                ]
                            elif img_meta["uuid"] in ss.gallery_selected_images:
                                del ss.gallery_selected_images[img_meta["uuid"]]
    else:
        image_display_placeholder.error(
            f"Failed to load images: {images_response_data}"
        )

# --- Custom CSS (remains the same) ---
st.markdown(
    f"""
<style>
    .image-grid-cell {{ width: 100%; padding-top: {THUMBNAIL_ASPECT_RATIO_PADDING}; position: relative; border-radius: 6px; margin-bottom: 5px; background-color: #f0f2f6; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow: hidden; }}
    .grid-thumbnail-image {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain; object-position: center; }}
    div[data-testid="stPopover"] > button {{ font-size: 0.8rem; padding: 3px 8px; border: 1px solid #d1d1d1; background-color: #f8f9fa; color: #212529; width: 100%; text-align: center; margin-top: 2px; }}
    div[data-testid="stPopover"] > button:hover {{ background-color: #e9ecef; border-color: #adb5bd; }}
    div[data-testid="stCheckbox"] {{ display: flex; justify-content: center; align-items: center; height: 100%; padding-top: 3px; margin-top: 2px; }}
    .faces-flex-container-popover {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 12px; padding: 5px; }}
    .face-crop-popover-item {{ text-align: center; }}
    .face-img-popover {{ width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid #e9ecef; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
</style>
""",
    unsafe_allow_html=True,
)
