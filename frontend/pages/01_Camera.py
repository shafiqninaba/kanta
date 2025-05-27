import streamlit as st
from PIL import Image
from utils.session import init_session_state, get_event_selection
from utils.api import upload_image

# ─────────────────────────────────────────────
# CONFIG & STATE
# ─────────────────────────────────────────────
st.set_page_config(page_title="Event Film Cam", page_icon="📸", layout="wide")

init_session_state()
get_event_selection()

MAX_PHOTOS = 20
ROWS, COLS = 4, 5

ss = st.session_state
ss.setdefault("captured_images", [])
ss.setdefault("uploaded_images", [])
ss.setdefault("selected_shots", set())

# ─────────────────────────────────────────────
# INTRO NOTE
# ─────────────────────────────────────────────
st.markdown("""
You can **upload existing images** to the event, or use the **film camera** below to take new photos.  
But remember — you only get **limited disposable shots**, so make them count!
""")

# ─────────────────────────────────────────────
# UPLOAD EXISTING PHOTOS EXPANDER
# ─────────────────────────────────────────────
with st.expander("Upload existing photos from disk", expanded=False):
    sel_files = st.file_uploader(
        "Choose images", type=["jpg", "jpeg", "png"], accept_multiple_files=True
    )
    if sel_files:
        cols = st.columns(3)
        for i, uf in enumerate(sel_files):
            with cols[i % 3]:
                st.image(uf, caption=f"Preview {i+1}", use_container_width=True)
        if st.button("Upload selected images", key="btn_bulk_upload"):
            ok, fails = 0, []
            prog = st.progress(0.0)
            for i, uf in enumerate(sel_files):
                r, suc = upload_image(ss.event_code, uf)
                if suc:
                    ok += 1
                else:
                    fails.append(f"Image {i+1}: {r}")
                prog.progress((i + 1) / len(sel_files))
            if ok:
                st.success(f"Uploaded {ok} image(s)")
            for msg in fails:
                st.error(msg)

st.markdown("---")

# ─────────────────────────────────────────────
# MAIN LAYOUT: CAMERA | FILM STRIP | BUTTONS
# ─────────────────────────────────────────────
cam_col, strip_col, btn_col = st.columns([2, 3, 1], gap="medium")

# --------------------------------------------
# CAMERA SECTION
# --------------------------------------------
with cam_col:
    st.subheader("📸 Film Camera")

    shots_used = len(ss.captured_images) + len(ss.uploaded_images)
    shots_left = MAX_PHOTOS - shots_used

    # Prominent shot counter
    st.markdown(
        f"""
    <div style='text-align: center; padding: 15px; background: #f0f2f6; border-radius: 10px; margin-bottom: 20px;'>
        <h3 style='margin: 0; color: #1f77b4; font-style: italic;'>
            {shots_left} shots remaining
        </h3>
    </div>
    """,
        unsafe_allow_html=True,
    )

    if shots_left > 0:
        cam_key = f"cam_{shots_used}"
        img_data = st.camera_input("Tap to capture (landscape preferred)", key=cam_key)
        if img_data:
            ss.captured_images.append(img_data)
            # Clear selections when new photo is taken
            ss.selected_shots = set()
            st.rerun()
    else:
        st.warning("🎞️ Film roll finished! Upload or delete shots to continue.")

# --------------------------------------------
# FILM STRIP SECTION (Sequential Order)
# --------------------------------------------
with strip_col:
    st.subheader("🎞️ Film Strip")

    # Combine all images in strict sequential order
    all_images = ss.captured_images + ss.uploaded_images
    total_pending = len(ss.captured_images)

    # Create grid slots
    total_slots = ROWS * COLS

    for r in range(ROWS):
        row = st.columns(COLS)
        for c in range(COLS):
            slot_idx = r * COLS + c
            with row[c]:
                if slot_idx < len(all_images):
                    img = all_images[slot_idx]
                    is_uploaded = slot_idx >= total_pending

                    # Create container for image with overlay
                    container_style = """
                    <div style='position: relative; border-radius: 8px; overflow: hidden;'>
                    """

                    if is_uploaded:
                        # Show uploaded indicator with green border and checkmark
                        st.markdown(
                            f"""
                        <div style='position: relative; border: 3px solid #28a745; border-radius: 8px; overflow: hidden;'>
                            <div style='position: absolute; top: 5px; right: 5px; 
                                        background: #28a745; color: white; border-radius: 50%; 
                                        width: 20px; height: 20px; display: flex; 
                                        align-items: center; justify-content: center;
                                        font-size: 12px; z-index: 10;'>✓</div>
                        """,
                            unsafe_allow_html=True,
                        )
                        st.image(img, use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        # Pending shot with selection checkbox
                        st.image(img, use_container_width=True)
                        is_selected = st.checkbox(
                            "", key=f"sel_{slot_idx}", label_visibility="collapsed"
                        )
                        if is_selected:
                            ss.selected_shots.add(slot_idx)
                        elif slot_idx in ss.selected_shots:
                            ss.selected_shots.discard(slot_idx)
                else:
                    # Empty slot
                    st.markdown(
                        """
                    <div style='border: 2px dashed #ccc; height: 120px; border-radius: 8px; 
                                display: flex; align-items: center; justify-content: center;
                                color: #999; font-size: 12px;'>
                        Empty
                    </div>
                    """,
                        unsafe_allow_html=True,
                    )

# --------------------------------------------
# BUTTONS SECTION
# --------------------------------------------
with btn_col:
    st.subheader("Actions")

    # Upload button
    if st.button("📤\nUpload", key="btn_upload", use_container_width=True):
        selected_indices = [i for i in ss.selected_shots if i < len(ss.captured_images)]

        if not selected_indices:
            st.warning("Select shots to upload first!")
        elif not ss.event_code:
            st.error("Select an event first!")
        else:
            ok, fails = 0, []
            # Sort in reverse to maintain indices when removing
            for idx in sorted(selected_indices, reverse=True):
                res, suc = upload_image(ss.event_code, ss.captured_images[idx])
                if suc:
                    ok += 1
                    # Move to uploaded list
                    ss.uploaded_images.append(ss.captured_images[idx])
                    ss.captured_images.pop(idx)
                else:
                    fails.append(f"Shot {idx+1}: {res}")

            # Clear selections
            ss.selected_shots = set()

            if ok:
                st.success(f"Uploaded {ok} shot(s)!")
            for msg in fails:
                st.error(msg)
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Delete button
    if st.button("🗑️\nDelete", key="btn_delete", use_container_width=True):
        selected_indices = [i for i in ss.selected_shots if i < len(ss.captured_images)]

        if not selected_indices:
            st.warning("Select shots to delete first!")
        else:
            # Sort in reverse to maintain indices when removing
            for idx in sorted(selected_indices, reverse=True):
                ss.captured_images.pop(idx)

            # Clear selections
            ss.selected_shots = set()
            st.success(f"Deleted {len(selected_indices)} shot(s)!")
            st.rerun()

# ─────────────────────────────────────────────
# CUSTOM STYLING
# ─────────────────────────────────────────────
st.markdown(
    """
<style>
/* Style the action buttons */
div[data-testid="column"] button[kind="secondary"] {
    height: 60px;
    font-weight: 600;
    border-radius: 8px;
    border: none;
    transition: all 0.2s;
}

/* Upload button - green */
div[data-testid="column"] button[key="btn_upload"] {
    background: linear-gradient(45deg, #28a745, #20c997) !important;
    color: white !important;
}

div[data-testid="column"] button[key="btn_upload"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(40, 167, 69, 0.3);
}

/* Delete button - red */
div[data-testid="column"] button[key="btn_delete"] {
    background: linear-gradient(45deg, #dc3545, #fd7e14) !important;
    color: white !important;
}

div[data-testid="column"] button[key="btn_delete"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(220, 53, 69, 0.3);
}

/* Checkbox styling */
div[data-testid="stCheckbox"] {
    margin-top: 5px;
}

/* Film strip styling */
div[data-testid="column"] img {
    border-radius: 6px;
    transition: transform 0.2s;
}

div[data-testid="column"] img:hover {
    transform: scale(1.02);
}
</style>
""",
    unsafe_allow_html=True,
)
