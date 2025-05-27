import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
import requests
from io import BytesIO
from datetime import datetime
import base64
import zipfile

from utils.api import get_images, get_image_detail
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
TINT_BLACK_SEPIA = "#704214"
TINT_WHITE_SEPIA = "#C0A080"

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


# --- Helper Function to fetch image bytes ---
@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_image_bytes_from_url(image_url: str) -> BytesIO | None:
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        return BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        print(
            f"Error fetching image data from {image_url[:60]}...: {e}"
        )  # Log for debugging
        return None


# --- Main Application ---
st.title("Image Gallery")
st.markdown(
    "Welcome to the Image Gallery! Explore images from your selected event. "
    "Use the filters below to refine your search, and click 'View Photo' for a closer look."
)

if not ss.get("event_code"):
    st.warning("👈 Please select an event from the sidebar to view images.")
    st.stop()

# --- Filter Bar ---
st.markdown("#### Filter Images")
filter_cols = st.columns(
    [1.5, 1.5, 0.8, 0.8, 0.8, 0.8, 1.5]
)  # 7th col for download button

with filter_cols[0]:
    date_from = st.date_input(
        "From",
        ss.gallery_date_from,
        key="gallery_filter_df",
        help="Images from this date.",
    )
with filter_cols[1]:
    date_to = st.date_input(
        "To",
        ss.gallery_date_to,
        key="gallery_filter_dt",
        help="Images up to this date.",
    )
with filter_cols[2]:
    min_faces = st.number_input(
        "Min Faces",
        0,
        value=ss.gallery_min_faces,
        key="gallery_filter_mf",
        help="0 for no min.",
        step=1,
    )
with filter_cols[3]:
    max_faces = st.number_input(
        "Max Faces",
        0,
        value=ss.gallery_max_faces,
        key="gallery_filter_maf",
        help="0 for no max.",
        step=1,
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
        "Page",
        1,
        value=ss.gallery_page,
        key="gallery_filter_p",
        help="Current page.",
        step=1,
    )

# Update session state (triggers rerun if values changed by user)
ss.gallery_date_from = date_from
ss.gallery_date_to = date_to
ss.gallery_min_faces = min_faces
ss.gallery_max_faces = max_faces
ss.gallery_limit = limit
ss.gallery_page = page

api_filter_params = {
    "date_from": f"{date_from}T00:00:00" if date_from else None,
    "date_to": f"{date_to}T23:59:59" if date_to else None,
    "min_faces": min_faces if min_faces > 0 else None,
    "max_faces": max_faces if max_faces > 0 else None,
    "limit": limit,
    "offset": (page - 1) * limit,
}

# --- Download Button Area ---
with filter_cols[6]:
    st.write("")
    st.write("")  # Vertical spacers

    # The number of selected images is determined by the current state of ss.gallery_selected_images
    # This state is updated when checkboxes are clicked and Streamlit reruns.
    num_selected_for_download_display = len(ss.gallery_selected_images)

    # Button to INITIATE the download preparation
    # Label does not show count to avoid looking like it's "stuck" if user perceives lag
    if st.button(
        "Download Selected",
        key="gallery_btn_prep_download",
        type="primary" if num_selected_for_download_display > 0 else "secondary",
        disabled=num_selected_for_download_display == 0,
        use_container_width=True,
        help="Prepare selected images for download.",
    ):
        # Re-check count *inside* the button click logic to ensure it's the latest
        num_to_prepare_on_click = len(ss.gallery_selected_images)
        if num_to_prepare_on_click > 0:
            ss.gallery_prepare_download_flag = True
            ss.gallery_download_ready_data = None  # Clear previous download data
            # st.rerun() # Rerun to trigger the preparation block below - this is key
        else:
            # This case should ideally not be hit if button is disabled, but a safeguard
            st.warning("No images selected to download.")
            ss.gallery_prepare_download_flag = False  # Ensure flag is false
        st.rerun()  # Rerun in all cases after button click to update UI based on flag

    # This block executes IF the flag was set in the PREVIOUS run (after the rerun from prepare button)
    if ss.get("gallery_prepare_download_flag", False):
        num_actually_preparing = len(
            ss.gallery_selected_images
        )  # Count for this preparation run
        if num_actually_preparing == 0:
            ss.gallery_prepare_download_flag = False  # Reset if nothing to prepare
            # No explicit rerun here, the lack of download_ready_data handles it
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
            ss.gallery_prepare_download_flag = (
                False  # Reset flag after preparation attempt
            )
            st.rerun()  # Rerun to ensure the actual download button appears or disappears correctly

    # Display the actual st.download_button if data has been prepared
    if ss.get("gallery_download_ready_data"):
        st.download_button(
            label=f"Click to Download: {ss.gallery_download_ready_filename}",
            data=ss.gallery_download_ready_data,
            file_name=ss.gallery_download_ready_filename,
            mime=ss.gallery_download_ready_mimetype,
            key="gallery_final_download_action_button",
            use_container_width=True,
            type="primary",  # CORRECTED: "success" is not a valid type
            on_click=lambda: ss.update(
                gallery_download_ready_data=None,  # Clear after click
                gallery_download_ready_filename=None,
                gallery_download_ready_mimetype=None,
            ),
        )

st.markdown("---")


# --- Image Detail Popover Content Function ---
def image_detail_popover_content_fn(image_uuid_for_popover: str):
    details_data, success = get_image_detail(image_uuid_for_popover)
    if not success:
        st.error(f"Details unavailable: {details_data}")
        return
    image_info = details_data.get("image", {})
    faces_info = details_data.get("faces", [])
    if not image_info:
        st.warning("Image metadata missing.")
        return

    st.image(
        image_info.get("azure_blob_url"), use_container_width=True
    )  # Show full image

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
                for face_meta in faces_info:  # Iterate through detected faces
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
                            pad_w, pad_h = (
                                int(w * 0.25),
                                int(h * 0.25),
                            )  # Padding around face
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
                            cropped_face_pil.save(
                                cropped_face_bytes, "PNG"
                            )  # Save as PNG
                            cropped_face_bytes.seek(0)
                            b64_img = base64.b64encode(
                                cropped_face_bytes.getvalue()
                            ).decode("utf-8")
                            faces_html_parts.append(  # HTML for each circular face image
                                f"<div class='face-crop-popover-item'>"
                                f"<img src='data:image/png;base64,{b64_img}' class='face-img-popover' alt='Detected Face'>"
                                f"</div>"
                            )
                        except Exception:
                            pass  # Silently skip errors for individual face crops
                if faces_html_parts:  # If any faces were successfully processed
                    st.markdown(
                        f"<div class='faces-flex-container-popover'>{''.join(faces_html_parts)}</div>",
                        unsafe_allow_html=True,
                    )
                elif (
                    len(faces_info) > 0
                ):  # If there were faces but none could be displayed
                    st.caption("Could not display face previews.")
            except Exception:  # Error opening main image for cropping
                st.caption("Note: Error preparing face display.")
        else:  # Original image bytes could not be fetched
            st.caption("Note: Original image data unavailable for face display.")


# --- Fetch and Display Images in Grid ---
if ss.event_code:
    image_display_placeholder = st.empty()
    image_display_placeholder.info("⏳ Loading images...")
    images_response_data, success = get_images(ss.event_code, **api_filter_params)

    if success:
        if not isinstance(images_response_data, list):
            image_display_placeholder.error(
                f"API Error: Expected list, got {type(images_response_data)}"
            )
            st.stop()

        fetched_images_list = images_response_data
        image_display_placeholder.empty()  # Clear "Loading..."

        if not fetched_images_list:
            st.info("No images found for the current filters.")
        else:
            st.write(
                f"Displaying {len(fetched_images_list)} image(s)."
            )  # User feedback

            grid_cols = st.columns(NUM_IMAGE_GRID_COLS)
            for i, img_meta in enumerate(fetched_images_list):
                with grid_cols[i % NUM_IMAGE_GRID_COLS]:
                    with st.container():  # Container for image and its controls
                        # HTML div for uniform thumbnail cell, with img tag inside for object-fit:contain
                        image_html_container = f"""
                        <div class="image-grid-cell" title="Faces: {img_meta['faces']}"> 
                             <img src="{img_meta['azure_blob_url']}" class="grid-thumbnail-image" alt="Image {img_meta['uuid'][:8]}">
                        </div>
                        """
                        st.markdown(image_html_container, unsafe_allow_html=True)

                        # Controls: "View Photo" Popover and "Select" Checkbox
                        controls_cols = st.columns([0.7, 0.3])  # Adjust ratio as needed
                        with controls_cols[0]:
                            with st.popover(
                                "View Photo",
                                use_container_width=True,
                                help=f"View full photo and details for {img_meta['uuid'][:8]}",
                            ):
                                image_detail_popover_content_fn(img_meta["uuid"])

                        with controls_cols[1]:
                            # Checkbox state reflects ss.gallery_selected_images
                            # Its change WILL trigger a rerun.
                            is_selected = st.checkbox(
                                "",
                                value=(img_meta["uuid"] in ss.gallery_selected_images),
                                key=f"gallery_select_img_{img_meta['uuid']}",
                                label_visibility="collapsed",
                                help="Select for download",
                            )
                            if is_selected:  # If checkbox is now checked
                                ss.gallery_selected_images[img_meta["uuid"]] = img_meta[
                                    "azure_blob_url"
                                ]
                            elif (
                                img_meta["uuid"] in ss.gallery_selected_images
                            ):  # If checkbox is now unchecked (and was previously in dict)
                                del ss.gallery_selected_images[img_meta["uuid"]]
    else:  # API call to get_images failed
        image_display_placeholder.error(
            f"Failed to load images: {images_response_data}"
        )

# --- Custom CSS ---
st.markdown(
    f"""
<style>
    /* Image Grid Cell - Outer div for fixed aspect ratio */
    .image-grid-cell {{
        width: 100%;
        padding-top: {THUMBNAIL_ASPECT_RATIO_PADDING}; /* e.g., 100% for square */
        position: relative; /* Crucial for positioning the inner img */
        border-radius: 6px;
        margin-bottom: 5px; /* Space before controls below the cell */
        background-color: #f0f2f6; /* Fallback/letterbox color */
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        overflow: hidden; /* Clip the inner img if it somehow overflows */
    }}
    /* The actual <img> tag inside the .image-grid-cell div */
    .grid-thumbnail-image {{
        position: absolute; 
        top: 0; left: 0; /* Position at top-left of parent */
        width: 100%; height: 100%; /* Fill the parent .image-grid-cell */
        object-fit: contain; /* Show whole image, letterbox if needed */
        object-position: center; /* Center image within the cell */
    }}

    /* Popover Button ("View Photo") */
    div[data-testid="stPopover"] > button {{
        font-size: 0.8rem; padding: 3px 8px; 
        border: 1px solid #d1d1d1; background-color: #f8f9fa; color: #212529;
        width: 100%; text-align: center; margin-top: 2px;
    }}
    div[data-testid="stPopover"] > button:hover {{
        background-color: #e9ecef; border-color: #adb5bd;
    }}

    /* Checkbox alignment */
    div[data-testid="stCheckbox"] {{ /* Targets the div Streamlit wraps checkbox in */
        display: flex; justify-content: center; align-items: center;
        height: 100%; /* Match height of popover button column */
        padding-top: 3px; /* Fine-tune vertical alignment */
        margin-top: 2px; /* Match popover button margin-top */
    }}
    
    /* Face Crop Styling in Popover */
    .faces-flex-container-popover {{ /* Flex container for faces */
        display: flex; flex-wrap: wrap; gap: 10px; 
        justify-content: center; margin-top: 12px; padding: 5px;
    }}
    .face-crop-popover-item {{ text-align: center; }} /* Each face item */
    .face-img-popover {{ /* The circular face image */
        width: 100px; height: 100px; /* Face image size */
        border-radius: 50%; object-fit: cover; /* Ensures circular crop */
        border: 2px solid #e9ecef; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
</style>
""",
    unsafe_allow_html=True,
)
