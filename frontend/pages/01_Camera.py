import streamlit as st
from PIL import Image, ImageEnhance, ImageOps
from utils.session import (
    init_session_state,
    get_event_selection,
)  # Assuming these are your utility functions
from utils.api import upload_image  # Assuming this is your API call utility
from io import BytesIO
import time  # time module is still used for camera capture naming and one sleep after camera processing

st.set_page_config(page_title="Event Film Cam", page_icon="📸", layout="wide")

# --- Constants ---
MAX_PHOTOS = 20  # Max shots for the disposable camera
FILM_STRIP_ROWS, FILM_STRIP_COLS = 4, 5  # Film strip grid dimensions

# --- Session State Initialization ---
ss = st.session_state
init_session_state()

ss.setdefault("captured_images", [])
ss.setdefault("uploaded_images", [])
ss.setdefault("current_filter", "Normal")
ss.setdefault("last_processed_img", None)

get_event_selection()


# --- Helper Functions ---
def calculate_shots_left():
    """Calculates remaining shots for the disposable camera."""
    return MAX_PHOTOS - (len(ss.captured_images) + len(ss.uploaded_images))


# --- Page Header ---
st.markdown(
    """
### 📷 How it works
- Use the **film camera** for a limited roll of disposable shots.
- Separately, you can **upload existing images** from your device directly to the event (no limit).
"""
)

# --- File Uploader (Expander) - Independent of Disposable Camera ---
with st.expander(
    "Upload existing photos from your device (no shot limit)",
    expanded=False,
):
    disk_files = st.file_uploader(
        "Choose images",  # Simplified label
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="disk_file_uploader_widget",
    )
    if disk_files:
        preview_cols = st.columns(min(len(disk_files), 4))
        for i, df in enumerate(disk_files):
            with preview_cols[i % len(preview_cols)]:
                st.image(df, caption=f"Preview {i+1}", use_container_width=True)

    if st.button(
        "Upload selected images from device", key="btn_disk_upload"
    ):  # Adjusted button label
        if not disk_files:
            st.warning("No files selected from device to upload.")
        elif not ss.get("event_code"):
            st.error("⚠️ Please select an event code first before uploading!")
        else:
            num_files_to_upload = len(disk_files)
            progress_bar = st.progress(
                0.0, text=f"Preparing to upload {num_files_to_upload} image(s)..."
            )

            ok_disk_uploads, failed_disk_uploads = 0, []

            for i, df in enumerate(disk_files):
                df.seek(0)
                upload_text = f"Uploading '{df.name}' ({i+1}/{num_files_to_upload})..."
                progress_bar.progress((i + 1) / num_files_to_upload, text=upload_text)

                res, success = upload_image(ss.event_code, df)

                if success:
                    ok_disk_uploads += 1
                else:
                    failed_disk_uploads.append(f"Image '{df.name}': {res}")

            progress_bar.empty()

            if ok_disk_uploads > 0:
                st.toast(
                    f"✅ Successfully uploaded {ok_disk_uploads} image(s) from device.",
                    icon="📤",
                )
            for msg in failed_disk_uploads:
                st.error(f"❌ Upload failed: {msg}")

st.divider()

# --- Disposable Camera Section ---
shots_left = calculate_shots_left()

counter_color = (
    "#ef476f" if shots_left <= 5 else ("#fca311" if shots_left <= 10 else "#eee")
)
st.markdown(
    f"""
<div style='font-family:monospace;font-size:18px;padding:8px;background:#222;color:{counter_color};border-radius:8px;text-align:center;margin-bottom:16px;'>
DISPOSABLE CAMERA: {shots_left} SHOT{"S" if shots_left != 1 else ""} REMAINING
</div>
""",
    unsafe_allow_html=True,
)

cam_col, strip_col = st.columns([2, 3], gap="medium")

with cam_col:
    st.subheader("📸 Film Camera")
    if shots_left > 0:
        img_file_buffer = st.camera_input(
            "Tap shutter (horizontal preferred)", key=f"camera_input_{shots_left}"
        )
    else:
        st.warning("🎞️ Disposable camera roll is full!")
        st.info("Delete some pending shots from the film strip to take more.")
        img_file_buffer = None

    ss.current_filter = st.selectbox(
        "Apply filter to new shot",  # Clarified label
        ["Normal", "Black & White", "Warm", "Cool", "Sepia"],
        index=["Normal", "B&W", "Warm", "Cool", "Sepia"].index(ss.current_filter),
        key="filter_selectbox",
    )

    if img_file_buffer and img_file_buffer != ss.last_processed_img:
        if (len(ss.captured_images) + len(ss.uploaded_images)) >= MAX_PHOTOS:
            st.error(
                "Film roll is full. Cannot capture new shot."
            )  # Should be rare if camera input is disabled
        else:
            with st.spinner("Processing image with filter..."):
                pil_image = Image.open(img_file_buffer).convert("RGB")
                active_filter = ss.current_filter
                if active_filter == "B&W":
                    pil_image = pil_image.convert("L").convert("RGB")
                elif active_filter == "Warm":
                    pil_image = Image.blend(
                        ImageEnhance.Color(pil_image).enhance(1.3),
                        Image.new("RGB", pil_image.size, (255, 230, 200)),
                        0.15,
                    )
                elif active_filter == "Cool":
                    pil_image = Image.blend(
                        ImageEnhance.Color(pil_image).enhance(0.9),
                        Image.new("RGB", pil_image.size, (200, 230, 255)),
                        0.15,
                    )
                elif active_filter == "Sepia":
                    pil_image = ImageOps.colorize(
                        pil_image.convert("L"), "#704214", "#C0A080"
                    )

                processed_buffer = BytesIO()
                pil_image.save(processed_buffer, "JPEG", quality=85)
                processed_buffer.seek(0)
                processed_buffer.name = (
                    f"capture_{int(time.time())}_{len(ss.captured_images)+1}.jpg"
                )
                ss.captured_images.append(processed_buffer)
                ss.last_processed_img = img_file_buffer

            st.toast(f"📸 Shot captured with {active_filter} filter!", icon="✨")
            st.rerun()

with strip_col:
    st.subheader("🎞️ Film Strip (Disposable Camera)")
    st.markdown(
        "Your captured shots appear here. Upload or delete pending shots using the buttons below."  # Slightly rephrased
    )

    film_strip_images = ss.captured_images + ss.uploaded_images
    num_pending_on_strip = len(ss.captured_images)
    film_strip_types = ["pending"] * num_pending_on_strip + ["uploaded"] * len(
        ss.uploaded_images
    )
    total_display_slots = FILM_STRIP_ROWS * FILM_STRIP_COLS
    display_images_in_grid = film_strip_images[:total_display_slots]
    display_types_in_grid = film_strip_types[:total_display_slots]

    while len(display_images_in_grid) < total_display_slots:
        display_images_in_grid.append(None)
        display_types_in_grid.append("empty")

    for r_idx in range(FILM_STRIP_ROWS):
        grid_cols = st.columns(FILM_STRIP_COLS)
        for c_idx in range(FILM_STRIP_COLS):
            current_slot_idx = r_idx * FILM_STRIP_COLS + c_idx
            img_data = display_images_in_grid[current_slot_idx]
            img_status = display_types_in_grid[current_slot_idx]
            with grid_cols[c_idx]:
                if img_status == "empty":
                    st.markdown(
                        "<div class='empty-film-slot'>Empty</div>",
                        unsafe_allow_html=True,
                    )
                elif img_status == "uploaded":
                    img_data.seek(0)
                    st.markdown(
                        "<div class='uploaded-indicator-wrapper'>",
                        unsafe_allow_html=True,
                    )
                    st.image(img_data, use_container_width=True)
                    st.markdown(
                        "<div class='uploaded-bar'>Uploaded</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)
                elif img_status == "pending":
                    img_data.seek(0)
                    st.image(img_data, use_container_width=True)
                    if current_slot_idx < num_pending_on_strip:
                        st.checkbox(
                            "",
                            key=f"sel_pending_{current_slot_idx}",
                            label_visibility="collapsed",
                        )
    st.divider()

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        btn_film_upload_label = "📤 Upload Selected Pending Shots"
        if st.button(
            btn_film_upload_label,  # Renamed button to match general "shots"
            key="btn_film_strip_upload",
            use_container_width=True,
            type="primary",
        ):
            if not ss.get("event_code"):
                st.error("⚠️ Please select an event code first before uploading!")
            else:
                selected_pending_indices = [
                    i
                    for i in range(num_pending_on_strip)
                    if ss.get(f"sel_pending_{i}", False)
                ]
                if not selected_pending_indices:
                    st.warning(
                        "No pending shots selected from the film strip for upload."
                    )
                else:
                    with st.spinner("Uploading selected shots..."):  # General "shots"
                        ok_film_uploads, fails_film_uploads = 0, []
                        for idx_in_captured_list in sorted(
                            selected_pending_indices, reverse=True
                        ):
                            img_to_upload = ss.captured_images[idx_in_captured_list]
                            img_to_upload.seek(0)
                            res, success = upload_image(ss.event_code, img_to_upload)

                            if success:
                                ok_film_uploads += 1
                                ss.uploaded_images.insert(
                                    0, ss.captured_images.pop(idx_in_captured_list)
                                )
                                if f"sel_pending_{idx_in_captured_list}" in ss:
                                    del ss[f"sel_pending_{idx_in_captured_list}"]
                            else:
                                fails_film_uploads.append(
                                    f"Pending Shot (approx. pos {idx_in_captured_list+1}): {res}"
                                )
                        if ok_film_uploads > 0:
                            st.toast(
                                f"✅ Uploaded {ok_film_uploads} pending shot(s) from film strip!",
                                icon="🚀",
                            )
                        for msg in fails_film_uploads:
                            st.error(f"❌ {msg}")
                        if ok_film_uploads > 0 or fails_film_uploads:
                            st.rerun()
    with action_col2:
        btn_film_delete_label = "🗑️ Delete Selected Pending Shots"
        if st.button(
            btn_film_delete_label,  # Renamed button
            key="btn_film_strip_delete",
            use_container_width=True,
            type="secondary",
        ):
            selected_pending_indices_del = [
                i
                for i in range(num_pending_on_strip)
                if ss.get(f"sel_pending_{i}", False)
            ]
            if not selected_pending_indices_del:
                st.warning(
                    "No pending shots selected from the film strip for deletion."
                )
            else:
                for idx_in_captured_list in sorted(
                    selected_pending_indices_del, reverse=True
                ):
                    ss.captured_images.pop(idx_in_captured_list)
                    if f"sel_pending_{idx_in_captured_list}" in ss:
                        del ss[f"sel_pending_{idx_in_captured_list}"]
                st.toast(
                    f"🗑️ Deleted {len(selected_pending_indices_del)} pending shot(s).",
                    icon="♻️",
                )
                st.rerun()

st.markdown(
    """
<style>
button[title="Clear photo"] { display: none !important; }
button[data-testid="baseButton-primary"] { background-color: #06d6a0 !important; color: white !important; border: none !important; font-weight: 600; border-radius: 8px; }
button[data-testid="baseButton-primary"]:hover { background-color: #05c794 !important; transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
button[data-testid="baseButton-secondary"] { background-color: #ef476f !important; color: white !important; border: none !important; font-weight: 600; border-radius: 8px; }
button[data-testid="baseButton-secondary"]:hover { background-color: #e63946 !important; transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.stImage > img { border-radius: 4px; object-fit: cover; }
.empty-film-slot { border: 2px dashed #555; height: 80px; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #888; font-size: 12px; background-color: rgba(200,200,200,0.1); }
.uploaded-indicator-wrapper { position: relative; border-radius: 4px; overflow: hidden; line-height: 0; }
.uploaded-indicator-wrapper .stImage > img { display: block !important; }
.uploaded-bar { position: absolute; bottom: 0; left: 0; width: 100%; background-color: rgba(6, 214, 160, 0.85); color: white; text-align: center; font-weight: bold; padding: 4px 0; font-size: 0.75em; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; box-sizing: border-box; }
div[data-testid="stCheckbox"] { padding-top: 2px; margin-left: auto; margin-right: auto; }
.stBlockLabel { font-weight: 500 !important; }
</style>
""",
    unsafe_allow_html=True,
)
