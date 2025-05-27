import streamlit as st
from PIL import Image, ImageEnhance, ImageOps
from utils.session import (
    init_session_state,
    get_event_selection,
)  # Assuming these are your utility functions
from utils.api import upload_image  # Assuming this is your API call utility
from io import BytesIO
import time

st.set_page_config(page_title="Event Film Cam", page_icon="📸", layout="wide")

# ─────────────────────────────────────────────
# INIT STATE
# ─────────────────────────────────────────────
init_session_state()  # Initializes ss.event_code, etc.
get_event_selection()  # Potentially updates ss.event_code from a sidebar

MAX_PHOTOS = 20
ROWS, COLS = 4, 5  # Film strip grid dimensions

ss = st.session_state
ss.setdefault("captured_images", [])  # List of BytesIO from camera, pending upload
ss.setdefault(
    "uploaded_images", []
)  # List of BytesIO (from camera) or UploadedFile (from disk) that are "on the film roll" and uploaded
ss.setdefault("current_filter", "Normal")
ss.setdefault("last_processed_img", None)  # To prevent re-processing same camera shot

# Calculate shots_left based on both pending and already uploaded images on the film roll
shots_left = MAX_PHOTOS - (len(ss.captured_images) + len(ss.uploaded_images))

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
### 📷 How it works
Upload existing images *or* use the **film camera**. You've got a limited roll – **make every shot count!**
""")

# ─────────────────────────────────────────────
# EVENT CODE CHECK
# ─────────────────────────────────────────────
if not ss.get("event_code"):
    st.error("⚠️ Please select an event code first before taking or uploading photos!")
    st.stop()

# ─────────────────────────────────────────────
# FILE UPLOADER (Expander) - Counts towards MAX_PHOTOS
# ─────────────────────────────────────────────
with st.expander(
    "Upload existing photos from disk (uses disposable shots)", expanded=False
):
    sel_files = st.file_uploader(
        "Choose images",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="disk_file_uploader",
    )
    if sel_files:
        preview_cols = st.columns(
            min(len(sel_files), 4)
        )  # Show up to 4 previews side-by-side
        for i, uf in enumerate(sel_files):
            with preview_cols[i % len(preview_cols)]:
                st.image(uf, caption=f"Preview {i+1}", use_container_width=True)

        if st.button("Upload selected images from disk", key="btn_bulk_upload"):
            if not ss.event_code:
                st.error("Please select an event code first!")
            else:
                with st.spinner("Uploading images from disk..."):
                    ok_disk, fails_disk = 0, []

                    for i, uf in enumerate(sel_files):
                        current_film_roll_count = len(ss.captured_images) + len(
                            ss.uploaded_images
                        )
                        if current_film_roll_count >= MAX_PHOTOS:
                            st.warning(
                                f"⚠️ Film roll full ({current_film_roll_count}/{MAX_PHOTOS}). Cannot upload '{uf.name}' or subsequent images."
                            )
                            break

                        uf.seek(0)
                        res, suc = upload_image(ss.event_code, uf)

                        if suc:
                            ok_disk += 1
                            uf.seek(0)
                            ss.uploaded_images.append(uf)
                        else:
                            fails_disk.append(f"Image '{uf.name}': {res}")
                        time.sleep(0.1)

                if ok_disk > 0:
                    # CORRECTED LINE:
                    st.toast(
                        f"✅ Successfully uploaded {ok_disk} image(s) from disk to the film roll!",
                        icon="📤",
                    )
                for msg in fails_disk:
                    st.error(f"❌ {msg}")

                if ok_disk > 0 or fails_disk:
                    st.rerun()

st.divider()

# ─────────────────────────────────────────────
# SHOTS COUNTER
# ─────────────────────────────────────────────
counter_color = (
    "#ef476f" if shots_left <= 5 else ("#fca311" if shots_left <= 10 else "#eee")
)  # Orange for medium, Red for low
st.markdown(
    f"""
<div style='font-family:monospace;font-size:18px;padding:8px;background:#222;color:{counter_color};border-radius:8px;text-align:center;margin-bottom:16px;'>
{shots_left} SHOT{"S" if shots_left != 1 else ""} REMAINING
</div>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# LAYOUT - 2 COLUMNS (Camera: 2 parts, Film Strip: 3 parts width)
# ─────────────────────────────────────────────
cam_col, strip_col = st.columns([2, 3], gap="medium")

# --------------------------------------------
# CAMERA COLUMN
# --------------------------------------------
with cam_col:
    st.subheader("📸 Film Camera")

    # Camera input - active if shots_left > 0
    if shots_left > 0:
        img_file = st.camera_input(
            "Tap shutter (horizontal preferred)", key=f"camera_input_{shots_left}"
        )
    else:
        st.warning("🎞️ Film roll exhausted! Upload or delete some shots to continue.")
        img_file = None  # Ensure img_file is None if camera is not shown

    # Filter selection
    ss.current_filter = st.selectbox(
        "Filter",
        ["Normal", "B&W", "Warm", "Cool", "Sepia"],
        index=["Normal", "B&W", "Warm", "Cool", "Sepia"].index(ss.current_filter),
        key="filter_selectbox",
    )

    # Process captured image
    if img_file and img_file != ss.last_processed_img:
        # This check is now redundant due to camera_input being conditional, but harmless
        if len(ss.captured_images) + len(ss.uploaded_images) >= MAX_PHOTOS:
            st.error(
                "🎞️ Film roll exhausted! (This message should ideally not appear if camera is disabled)"
            )
        else:
            with st.spinner("Processing image..."):
                pil = Image.open(img_file).convert("RGB")
                f = ss.current_filter

                if f == "B&W":
                    pil = pil.convert("L").convert("RGB")
                elif f == "Warm":
                    pil = Image.blend(
                        ImageEnhance.Color(pil).enhance(1.3),
                        Image.new("RGB", pil.size, (255, 230, 200)),
                        0.15,
                    )
                elif f == "Cool":
                    pil = Image.blend(
                        ImageEnhance.Color(pil).enhance(0.9),
                        Image.new("RGB", pil.size, (200, 230, 255)),
                        0.15,
                    )
                elif f == "Sepia":
                    pil = ImageOps.colorize(pil.convert("L"), "#704214", "#C0A080")

                buf = BytesIO()
                pil.save(buf, "JPEG", quality=85)
                buf.seek(0)
                # Giving a more unique name for potential debugging, though not strictly necessary for BytesIO
                buf.name = f"capture_{int(time.time())}_{len(ss.captured_images)+1}.jpg"

                ss.captured_images.append(buf)
                ss.last_processed_img = img_file

                time.sleep(0.5)

            st.toast(f"📸 Shot captured with {f} filter!", icon="✨")
            st.rerun()

# --------------------------------------------
# FILM STRIP + ACTIONS
# --------------------------------------------
with strip_col:
    st.subheader("🎞️ Film Strip")
    st.markdown("Here are your shots. Pending uploads are marked with a checkbox.")

    # Build image list: pending captured, then already uploaded (from camera or disk)
    # Ensure they are sorted if order matters within these groups (e.g., by timestamp if available)
    # For simplicity here, captured_images are appended, then uploaded_images are appended.
    all_images_on_strip = ss.captured_images + ss.uploaded_images

    # Determine type for styling/checkboxes
    # 'pending' are from ss.captured_images, 'uploaded' are from ss.uploaded_images
    num_pending = len(ss.captured_images)
    all_types_on_strip = ["pending"] * num_pending + ["uploaded"] * len(
        ss.uploaded_images
    )

    total_slots = ROWS * COLS  # Max slots to display in the grid

    display_images = all_images_on_strip[:total_slots]
    display_types = all_types_on_strip[:total_slots]

    # Fill remaining display slots with 'empty' if fewer images than total_slots
    while len(display_images) < total_slots:
        display_images.append(None)
        display_types.append("empty")

    for r in range(ROWS):
        grid_cols = st.columns(COLS)
        for c in range(COLS):
            idx_in_grid = r * COLS + c
            img_obj = display_images[idx_in_grid]
            img_type = display_types[idx_in_grid]

            with grid_cols[c]:
                if img_type == "empty":
                    st.markdown(
                        "<div class='empty-film-slot'>Empty</div>",
                        unsafe_allow_html=True,
                    )
                elif img_type == "uploaded":
                    img_obj.seek(0)
                    # Wrapper for green bar indicator
                    st.markdown(
                        "<div class='uploaded-indicator-wrapper'>",
                        unsafe_allow_html=True,
                    )
                    st.image(img_obj, use_container_width=True)
                    st.markdown(
                        "<div class='uploaded-bar'>Uploaded</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)
                else:  # 'pending'
                    img_obj.seek(0)
                    st.image(img_obj, use_container_width=True)
                    # Checkbox is for images in ss.captured_images, its index is `idx_in_grid`
                    # as long as `idx_in_grid` is less than `num_pending`.
                    if (
                        idx_in_grid < num_pending
                    ):  # Only show checkbox for actual pending images
                        st.checkbox(
                            "",
                            key=f"sel_pending_{idx_in_grid}",
                            label_visibility="collapsed",
                        )
    st.divider()

    # Action buttons for film strip (Upload/Delete PENDING shots)
    action_col1, action_col2 = st.columns(2)

    with action_col1:
        if st.button(
            "📤 Upload Selected Pending",
            key="btn_film_strip_upload",
            use_container_width=True,
            type="primary",
        ):
            selected_pending_indices = [
                i for i in range(num_pending) if ss.get(f"sel_pending_{i}", False)
            ]

            if not selected_pending_indices:
                st.warning("No pending shots selected for upload.")
            elif not ss.event_code:  # Should be caught by global check
                st.error("Please select an event code first!")
            else:
                with st.spinner("Uploading selected pending shots..."):
                    ok_film_upload, fails_film_upload = 0, []
                    # Process in reverse to handle .pop() correctly
                    for idx in sorted(selected_pending_indices, reverse=True):
                        img_to_upload = ss.captured_images[idx]
                        img_to_upload.seek(0)
                        res, suc = upload_image(ss.event_code, img_to_upload)
                        time.sleep(0.2)  # UX delay

                        if suc:
                            ok_film_upload += 1
                            # Move from captured_images to uploaded_images
                            ss.uploaded_images.insert(
                                0, ss.captured_images.pop(idx)
                            )  # Insert at start of uploaded to keep them visible
                            if f"sel_pending_{idx}" in ss:
                                del ss[f"sel_pending_{idx}"]
                        else:
                            fails_film_upload.append(f"Shot {idx+1}: {res}")

                    if ok_film_upload > 0:
                        st.toast(
                            f"✅ Uploaded {ok_film_upload} pending shot(s)!", icon="🚀"
                        )
                    for msg in fails_film_upload:
                        st.error(f"❌ {msg}")

                    if ok_film_upload > 0 or fails_film_upload:
                        st.rerun()
    with action_col2:
        if st.button(
            "🗑️ Delete Selected Pending",
            key="btn_film_strip_delete",
            use_container_width=True,
            type="secondary",
        ):
            selected_pending_indices_del = [
                i for i in range(num_pending) if ss.get(f"sel_pending_{i}", False)
            ]
            if not selected_pending_indices_del:
                st.warning("No pending shots selected for deletion.")
            else:
                for idx in sorted(selected_pending_indices_del, reverse=True):
                    ss.captured_images.pop(idx)
                    if f"sel_pending_{idx}" in ss:
                        del ss[f"sel_pending_{idx}"]

                st.toast(
                    f"🗑️ Deleted {len(selected_pending_indices_del)} pending shot(s).",
                    icon="♻️",
                )
                st.rerun()

# ─────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────
st.markdown(
    """
<style>
/* Hide the default "Clear photo" button from st.camera_input */
button[title="Clear photo"] {
    display: none !important;
}

/* Custom Button Styling */
button[data-testid="baseButton-primary"] { /* More specific selector for Streamlit 1.30+ */
    background-color: #06d6a0 !important; /* Bright Green */
    color: white !important;
    border: none !important;
    font-weight: 600;
    border-radius: 8px;
}
button[data-testid="baseButton-primary"]:hover {
    background-color: #05c794 !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
button[data-testid="baseButton-secondary"] { /* More specific selector */
    background-color: #ef476f !important; /* Bright Red */
    color: white !important;
    border: none !important;
    font-weight: 600;
    border-radius: 8px;
}
button[data-testid="baseButton-secondary"]:hover {
    background-color: #e63946 !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

/* Film Strip Styling */
.stImage > img { /* Target images within Streamlit's image container */
    border-radius: 4px; /* Rounded corners for all images in strip */
    object-fit: cover; /* Ensure images cover their allocated space well */
}
.empty-film-slot {
    border: 2px dashed #555;
    height: 80px; /* Adjusted height */
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #888;
    font-size: 12px;
    background-color: rgba(200,200,200,0.1);
}

/* Uploaded Image Indicator Styling */
.uploaded-indicator-wrapper {
    position: relative; /* Context for the absolute positioned bar */
    border-radius: 4px; /* Match image radius */
    overflow: hidden; /* Clip the bar if it somehow extends */
    line-height: 0; /* Helps remove extra space around image sometimes */
}
.uploaded-indicator-wrapper .stImage > img {
    display: block !important; /* Critical for removing bottom space for the bar */
}
.uploaded-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    background-color: rgba(6, 214, 160, 0.85); /* #06d6a0 with alpha - same as primary button */
    color: white;
    text-align: center;
    font-weight: bold;
    padding: 4px 0;
    font-size: 0.75em; /* Slightly smaller font for the bar */
    border-bottom-left-radius: 4px; /* Match wrapper/image radius */
    border-bottom-right-radius: 4px; /* Match wrapper/image radius */
    box-sizing: border-box;
}

/* Checkbox styling for better alignment if needed */
div[data-testid="stCheckbox"] {
    padding-top: 2px; /* Adjust spacing around checkbox */
    margin-left: auto; /* Attempt to center or align right if container is flex */
    margin-right: auto;
}

/* General layout improvements */
.stApp { /* Target the main app container */
    /* background-color: #f0f2f6; /* Example: Light gray background for the whole app */
}
.stBlockLabel { /* Labels for widgets like selectbox, file_uploader */
    font-weight: 500 !important;
}

</style>
""",
    unsafe_allow_html=True,
)
