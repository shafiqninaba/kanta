"""
Image Gallery page for Streamlit application.

Allows filtering, selection, bulk download, and detailed inspection of images.
"""

import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Union

import streamlit as st

from utils.api import get_image_detail, get_images
from utils.image import crop_and_encode_face, fetch_image_bytes_from_url
from utils.session import get_event_selection, init_session_state

# Page Configuration
st.set_page_config(page_title="Image Gallery", page_icon="🖼️", layout="wide")

# --------------------------------------------------------------------
# Constants and Defaults
# --------------------------------------------------------------------
IMAGES_PER_PAGE_OPTIONS: List[int] = [10, 20, 30, 50, 100]
DEFAULT_IMAGES_PER_PAGE: int = 20
NUM_GRID_COLS: int = 5
THUMBNAIL_ASPECT_PADDING: str = "100%"
CLUSTER_ID_UNASSIGNED: int = -1
CLUSTER_ID_PROCESSING: int = -2

# --------------------------------------------------------------------
# Session State Initialization
# --------------------------------------------------------------------
init_session_state()
get_event_selection()
ss = st.session_state

ss.setdefault("gallery_date_from", None)
ss.setdefault("gallery_date_to", None)
ss.setdefault("gallery_min_faces", 0)
ss.setdefault("gallery_max_faces", 0)
ss.setdefault("gallery_limit", DEFAULT_IMAGES_PER_PAGE)
ss.setdefault("gallery_page", 1)
ss.setdefault("gallery_selected_images", {})
ss.setdefault("gallery_prepare_download", False)
ss.setdefault("gallery_download_data", None)
ss.setdefault("gallery_download_filename", None)
ss.setdefault("gallery_download_mime", None)
ss.setdefault("gallery_filter_clusters", None)
ss.setdefault("gallery_face_selections", {})

# --------------------------------------------------------------------
# Page Title and Cluster Filter Notice
# --------------------------------------------------------------------
st.title("Image Gallery")
active_clusters = ss.gallery_filter_clusters
if active_clusters:
    ids = ", ".join(map(str, sorted(set(active_clusters))))
    st.info(f"ℹ️ Showing images for persons: {ids}.")

# --------------------------------------------------------------------
# Event Selection Check
# --------------------------------------------------------------------
if not ss.get("event_code"):
    st.warning("👈 Select an event from the sidebar to view images.")
    st.stop()

# --------------------------------------------------------------------
# Filter Bar
# --------------------------------------------------------------------
st.markdown("#### Filter Images")
cols = st.columns([1.5, 1.5, 1, 1, 1, 1, 1, 1.5])

# Date filters
date_from = cols[0].date_input("From", ss.gallery_date_from)
date_to = cols[1].date_input("To", ss.gallery_date_to)
# Face count filters
min_faces = cols[2].number_input("Min", min_value=0, value=ss.gallery_min_faces)
max_faces = cols[3].number_input("Max", min_value=0, value=ss.gallery_max_faces)
# Pagination filters
limit = cols[4].selectbox(
    "Limit",
    IMAGES_PER_PAGE_OPTIONS,
    index=IMAGES_PER_PAGE_OPTIONS.index(ss.gallery_limit),
    key="gallery_filter_limit",
)
page = cols[5].number_input(
    "Page", min_value=1, value=ss.gallery_page, key="gallery_filter_page"
)

# Clear people filter or placeholder
action_col = cols[6]
if active_clusters:
    if action_col.button(
        "Clear People Filter",
        key="clear_gallery_cluster_filter",
        use_container_width=True,
        help="Remove the person-based filter.",
    ):
        ss.gallery_filter_clusters = None
        ss.gallery_page = 1
        ss.gallery_face_selections.clear()
        st.rerun()
else:
    action_col.markdown("<div style='height:38px'></div>", unsafe_allow_html=True)

# Download selected button
download_col = cols[7]
selected_count = len(ss.gallery_selected_images)
if download_col.button(
    "Download Selected",
    key="gallery_btn_prep_download",
    type="primary" if selected_count > 0 else "secondary",
    disabled=(selected_count == 0),
    use_container_width=True,
):
    ss.gallery_prepare_download = True
    st.rerun()

# Update session state on filter changes
filters_changed = False
for var, new in [
    ("gallery_date_from", date_from),
    ("gallery_date_to", date_to),
    ("gallery_min_faces", min_faces),
    ("gallery_max_faces", max_faces),
]:
    if ss.get(var) != new:
        ss[var] = new
        filters_changed = True
ss.gallery_limit = limit
ss.gallery_page = page
if filters_changed and ss.gallery_filter_clusters:
    ss.gallery_filter_clusters = None
    ss.gallery_face_selections.clear()
    ss.gallery_page = 1

# Prepare API filter parameters
api_params: Dict[str, Union[str, int, List[int], None]] = {
    "date_from": f"{date_from}T00:00:00" if date_from else None,
    "date_to": f"{date_to}T23:59:59" if date_to else None,
    "min_faces": min_faces or None,
    "max_faces": max_faces or None,
    "limit": limit,
    "offset": (page - 1) * limit,
    "cluster_list_id": ss.gallery_filter_clusters,
}

# --------------------------------------------------------------------
# Download Preparation Logic
# --------------------------------------------------------------------
if ss.gallery_prepare_download:
    selection = ss.gallery_selected_images
    count = len(selection)
    if count == 0:
        st.warning("No images selected.")
        ss.gallery_prepare_download = False
        st.rerun()
    with st.spinner(f"Preparing {count} image(s)..."):
        if count == 1:
            uuid, url = next(iter(selection.items()))
            data = fetch_image_bytes_from_url(url)
            if data:
                ext = url.split(".")[-1].lower()[:4]
                ss.gallery_download_data = data
                ss.gallery_download_filename = f"{ss.event_code}_{uuid}.{ext}"
                ss.gallery_download_mime = f"image/{ext}"
        else:
            buf = BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for uuid, url in selection.items():
                    data = fetch_image_bytes_from_url(url)
                    if data:
                        ext = url.split(".")[-1].lower()[:4]
                        zf.writestr(f"{ss.event_code}_{uuid}.{ext}", data.getvalue())
            buf.seek(0)
            ss.gallery_download_data = buf
            ss.gallery_download_filename = f"{ss.event_code}_selected.zip"
            ss.gallery_download_mime = "application/zip"
    ss.gallery_prepare_download = False
    st.toast("Download ready!", icon="✅")
    st.rerun()

# Show download button if ready
if ss.gallery_download_data:
    st.download_button(
        label=f"Download: {ss.gallery_download_filename}",
        data=ss.gallery_download_data,
        file_name=ss.gallery_download_filename,
        mime=ss.gallery_download_mime,
        use_container_width=True,
        key="gallery_download_button",
        on_click=lambda: ss.pop("gallery_download_data", None),
    )

st.markdown("---")


# --------------------------------------------------------------------
# Image Detail Popover Content
# --------------------------------------------------------------------
def image_detail_popover(image_uuid: str) -> None:
    """
    Display detailed view and face-selection for a given image UUID.
    """
    details = get_image_detail(image_uuid)
    if not details:
        st.error("Details unavailable.")
        return
    info = details.get("image", {})
    faces = details.get("faces", [])

    st.image(info.get("azure_blob_url"), use_column_width=True)
    created = info.get("created_at")
    if created:
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            st.caption(dt.strftime("%b %d, %Y %H:%M"))
        except Exception:
            st.caption(created)
    st.caption(f"Faces: {len(faces)} | Type: {info.get('file_extension','').upper()}")

    if not faces:
        st.caption("No faces in this image.")
        return

    stream = fetch_image_bytes_from_url(info.get("azure_blob_url"))
    if not stream:
        st.error("Cannot load image for face cropping.")
        return

    selections = ss.gallery_face_selections.setdefault(image_uuid, {})
    valid_clusters: List[int] = []

    for idx, face in enumerate(faces):
        bbox = face.get("bbox", {})
        cid = face.get("cluster_id")
        fid = face.get("uuid", f"face_{idx}")

        # Face thumbnail
        if all(k in bbox for k in ("x", "y", "width", "height")):
            buf = BytesIO(stream.getvalue())
            b64 = crop_and_encode_face(buf, bbox, (60, 60), 0.15, 0.15)
            if b64:
                st.markdown(
                    f"<div class='popover-face-image'><img src='{b64}'></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div class='popover-face-placeholder'>Face</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div class='popover-face-placeholder'>Face</div>",
                unsafe_allow_html=True,
            )

        # Selection or status indicator
        key = f"filter_btn_popover_{image_uuid}_{fid}_{idx}"
        if cid in (CLUSTER_ID_UNASSIGNED, CLUSTER_ID_PROCESSING):
            text = "Unidentified" if cid == CLUSTER_ID_UNASSIGNED else "Processing"
            st.markdown(
                f"<div class='popover-face-status'>{text}</div>", unsafe_allow_html=True
            )
            selections[idx] = {"selected": False, "cluster_id": cid}
        else:
            prev = selections.get(idx, {}).get("selected", False)
            cur = st.checkbox(
                f"Person {cid}", value=prev, key=key, help=f"Select Person ID {cid}"
            )
            selections[idx] = {"selected": cur, "cluster_id": cid}
            if cur:
                valid_clusters.append(cid)

        if idx < len(faces) - 1:
            st.markdown("---")

    unique_clusters = sorted(set(valid_clusters))
    if st.button(
        f"Filter by these {len(unique_clusters)} Person(s)",
        key=f"apply_popover_filter_{image_uuid}",
        disabled=not unique_clusters,
        use_container_width=True,
        type="primary",
    ):
        ss.gallery_filter_clusters = unique_clusters
        ss.gallery_page = 1
        ss.gallery_date_from = ss.gallery_date_to = None
        ss.gallery_min_faces = ss.gallery_max_faces = 0
        st.rerun()


# --------------------------------------------------------------------
# Fetch and Display Image Grid
# --------------------------------------------------------------------
images = get_images(ss.event_code, **api_params)
if not isinstance(images, list):
    st.error(f"API Error: Expected list, got {type(images)}")
    st.stop()

if not images:
    msg = (
        "No images for selected people."
        if active_clusters
        else "No images match filters."
    )
    st.info(msg)
else:
    st.write(f"Displaying {len(images)} image(s).")
    cols = st.columns(NUM_GRID_COLS)

    for idx, img in enumerate(images):
        with cols[idx % NUM_GRID_COLS]:
            st.markdown(
                f"""
<div class='image-grid-cell' title='Faces: {img['faces']}'>
  <img src='{img['azure_blob_url']}' class='grid-thumbnail-image'>
</div>
""",
                unsafe_allow_html=True,
            )
            ctrl = st.columns([0.7, 0.3])
            with ctrl[0]:
                with st.popover("View Photo", use_container_width=True):
                    image_detail_popover(img["uuid"])
            with ctrl[1]:
                sel_key = f"gallery_select_{img['uuid']}"
                sel = img["uuid"] in ss.gallery_selected_images
                new = st.checkbox(
                    "", value=sel, key=sel_key, label_visibility="collapsed"
                )
                if new:
                    ss.gallery_selected_images[img["uuid"]] = img["azure_blob_url"]
                elif sel:
                    del ss.gallery_selected_images[img["uuid"]]

# --------------------------------------------------------------------
# Custom CSS
# --------------------------------------------------------------------
st.markdown(
    f"""
<style>
.image-grid-cell {{ width:100%; padding-top: {THUMBNAIL_ASPECT_PADDING}; position:relative; border-radius:6px; background:#f0f2f6; box-shadow:0 1px 3px rgba(0,0,0,0.08); overflow:hidden; margin-bottom:5px; }}
.grid-thumbnail-image {{ position:absolute; top:0; left:0; width:100%; height:100%; object-fit:contain; }}
.popover-face-image img {{ border-radius:50%; width:60px; height:60px; }}
.popover-face-placeholder {{ border:1px solid #ccc; border-radius:50%; width:60px; height:60px; background:#e0e0e0; display:flex; align-items:center; justify-content:center; color:#555; font-size:0.8em; }}
.popover-face-status {{ text-align:center; font-size:0.85em; color:#6c757d; margin-bottom:5px; }}
</style>
""",
    unsafe_allow_html=True,
)
