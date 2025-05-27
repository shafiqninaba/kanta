import time
import streamlit as st
from io import BytesIO
from PIL import Image, ImageEnhance, ImageOps
from utils.session import init_session_state, get_event_selection
from utils.api import (
    upload_image,
)  # Expects upload_image(event_code, file_buffer) -> (result_message, success_boolean)

# --- Page Configuration ---
st.set_page_config(page_title="Event Film Cam", page_icon="📸", layout="wide")

# --- Application Constants ---
MAX_DISPOSABLE_SHOTS = 20
FILM_STRIP_ROWS, FILM_STRIP_COLS = 4, 5
IMAGE_FILTERS = ["Normal", "Black & White", "Warm", "Cool", "Sepia"]

# --- Session State Initialization ---
ss = st.session_state
init_session_state()  # Initializes ss.event_code, etc.

# Specific state for this page
ss.setdefault(
    "pending_camera_shots", []
)  # List of BytesIO from camera, awaiting upload
ss.setdefault(
    "uploaded_camera_shots", []
)  # List of BytesIO (originated from camera) that are uploaded
ss.setdefault("current_image_filter", "Normal")
ss.setdefault(
    "last_processed_camera_frame", None
)  # To prevent re-processing the same camera frame

get_event_selection()  # Updates ss.event_code from sidebar or other global selection mechanism


# --- Helper Function for Image Filtering ---
def apply_filter_to_image(image: Image.Image, filter_mode: str) -> Image.Image:
    """Applies the selected visual filter to a PIL Image object."""
    if filter_mode == "Black & White":
        return image.convert("L").convert("RGB")
    if filter_mode == "Warm":
        enhancer = ImageEnhance.Color(image)
        colored_image = enhancer.enhance(1.3)
        warm_overlay = Image.new("RGB", image.size, (255, 230, 200))
        return Image.blend(colored_image, warm_overlay, 0.15)
    if filter_mode == "Cool":
        enhancer = ImageEnhance.Color(image)
        colored_image = enhancer.enhance(0.9)
        cool_overlay = Image.new("RGB", image.size, (200, 230, 255))
        return Image.blend(colored_image, cool_overlay, 0.15)
    if filter_mode == "Sepia":
        # Ensure image is in a mode that colorize can handle (e.g., 'L')
        return ImageOps.colorize(image.convert("L"), black="#704214", white="#C0A080")
    return image  # 'Normal' or unknown filter


# --- Page Header and Instructions ---
st.markdown(
    """
### 📷 How it works
- Use the **film camera** for a limited roll of disposable shots.
- Separately, you can **upload existing images** from your device directly to the event (no limit).
"""
)

# --- Section: Upload Existing Photos from Device ---
with st.expander(
    "Upload existing photos from your device (no shot limit)", expanded=False
):
    device_files = st.file_uploader(
        "Choose images",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="device_file_uploader",  # Descriptive key
    )
    if device_files:
        # Display previews for selected device files
        preview_cols = st.columns(min(len(device_files), 4))  # Max 4 previews in a row
        for i, uploaded_file in enumerate(device_files):
            with preview_cols[i % len(preview_cols)]:
                try:
                    st.image(
                        uploaded_file,
                        caption=uploaded_file.name,
                        use_container_width=True,
                    )
                except Exception as e:
                    st.caption(f"Preview error for {uploaded_file.name}: {e}")

    if st.button("Upload selected images from device", key="btn_device_file_upload"):
        if not device_files:
            st.warning("No files selected from device to upload.")
        elif not ss.get("event_code"):
            st.error("⚠️ Please select an event code first before uploading!")
        else:
            num_to_upload = len(device_files)
            progress_bar = st.progress(
                0.0, text=f"Preparing to upload {num_to_upload} image(s)..."
            )
            successful_uploads, failed_upload_details = 0, []

            for i, file_to_upload in enumerate(device_files, start=1):
                try:
                    file_to_upload.seek(0)  # Reset file pointer before each use
                    upload_status_text = (
                        f"Uploading '{file_to_upload.name}' ({i}/{num_to_upload})..."
                    )
                    progress_bar.progress(i / num_to_upload, text=upload_status_text)

                    # upload_image function should handle the UploadedFile object directly
                    result_message, was_successful = upload_image(
                        ss.event_code, file_to_upload
                    )

                    if was_successful:
                        successful_uploads += 1
                    else:
                        failed_upload_details.append(
                            f"'{file_to_upload.name}': {result_message}"
                        )
                except Exception as e:
                    failed_upload_details.append(
                        f"'{file_to_upload.name}': Critical error during upload process - {e}"
                    )

            progress_bar.empty()  # Remove progress bar after completion

            if successful_uploads > 0:
                st.toast(
                    f"✅ Successfully uploaded {successful_uploads}/{num_to_upload} image(s) from device.",
                    icon="📤",
                )
            if failed_upload_details:
                st.error(f"❌ Failed to upload {len(failed_upload_details)} image(s):")
                for error_detail in failed_upload_details:
                    st.caption(f" - {error_detail}")  # Use caption for a list of errors

st.divider()  # Visual separator

# --- Section: Disposable Camera ---

# Calculate remaining shots directly
shots_left_on_roll = MAX_DISPOSABLE_SHOTS - (
    len(ss.pending_camera_shots) + len(ss.uploaded_camera_shots)
)

# Determine color for the shots counter based on remaining shots
if shots_left_on_roll <= 5:
    counter_color = "#ef476f"  # Red for low
elif shots_left_on_roll <= 10:
    counter_color = "#fca311"  # Orange for medium
else:
    counter_color = "#eee"  # Default color

st.markdown(
    f"""
<div style='font-family:monospace;font-size:18px;padding:8px;background:#222;color:{counter_color};border-radius:8px;text-align:center;margin-bottom:16px;'>
DISPOSABLE CAMERA: {shots_left_on_roll} SHOT{'S' if shots_left_on_roll != 1 else ''} REMAINING
</div>
""",
    unsafe_allow_html=True,
)

# Layout for camera input and film strip
camera_column, film_strip_column = st.columns([2, 3], gap="medium")

with camera_column:
    st.subheader("📸 Film Camera")

    # Use a dynamic key for camera_input to help reset it if shots_left_on_roll changes
    camera_widget_key = f"camera_input_widget_{shots_left_on_roll}"

    if shots_left_on_roll > 0:
        camera_shot_buffer = st.camera_input(
            "Tap shutter (horizontal preferred)", key=camera_widget_key
        )
    else:
        st.warning("🎞️ Disposable camera roll is full!")
        st.info("Delete some pending shots from the film strip to take more.")
        camera_shot_buffer = None  # No camera input if roll is full

    # Filter selection for new shots
    ss.current_image_filter = st.selectbox(
        "Apply filter to new shot:",  # Added colon for clarity
        IMAGE_FILTERS,
        index=IMAGE_FILTERS.index(ss.current_image_filter),  # Pre-select current filter
        key="image_filter_selector",
    )

    # Process a newly captured camera shot
    if camera_shot_buffer and camera_shot_buffer != ss.last_processed_camera_frame:
        # Double-check shot limit before processing
        if (
            len(ss.pending_camera_shots) + len(ss.uploaded_camera_shots)
        ) >= MAX_DISPOSABLE_SHOTS:
            st.error("Film roll is full. Cannot capture new shot.")  # Safeguard
        else:
            with st.spinner("Processing image with filter..."):
                try:
                    pil_photo = Image.open(camera_shot_buffer).convert("RGB")
                    filtered_photo = apply_filter_to_image(
                        pil_photo, ss.current_image_filter
                    )

                    # Save processed photo to a BytesIO buffer
                    photo_buffer_for_strip = BytesIO()
                    filtered_photo.save(photo_buffer_for_strip, "JPEG", quality=85)
                    photo_buffer_for_strip.seek(0)  # Reset buffer pointer
                    photo_buffer_for_strip.name = (
                        f"shot_{int(time.time())}_{len(ss.pending_camera_shots)+1}.jpg"
                    )

                    ss.pending_camera_shots.append(photo_buffer_for_strip)
                    ss.last_processed_camera_frame = (
                        camera_shot_buffer  # Mark this frame as processed
                    )

                    # st.toast automatically disappears. No need for time.sleep if the goal is just notification.
                    st.toast(
                        f"📸 Shot captured with {ss.current_image_filter} filter!",
                        icon="✨",
                    )
                    st.rerun()  # Rerun to update film strip, shot counter, and camera state
                except Exception as e:
                    st.error(f"Error processing camera image: {e}")

with film_strip_column:
    st.subheader("🎞️ Film Strip (Disposable Camera)")
    st.markdown(
        "Your captured shots. Upload or delete pending shots using the buttons below."
    )

    # Combine pending and uploaded camera shots for display
    film_strip_all_shots = ss.pending_camera_shots + ss.uploaded_camera_shots
    num_pending_shots_on_strip = len(ss.pending_camera_shots)

    # Determine the status ('pending' or 'uploaded') for each shot on the strip
    film_strip_shot_types = ["pending"] * num_pending_shots_on_strip + [
        "uploaded"
    ] * len(ss.uploaded_camera_shots)

    total_grid_slots = FILM_STRIP_ROWS * FILM_STRIP_COLS

    # Prepare lists for actual grid display, padded with None/'empty' if needed
    grid_shots_to_display = film_strip_all_shots[:total_grid_slots]
    grid_shot_types_to_display = film_strip_shot_types[:total_grid_slots]

    while len(grid_shots_to_display) < total_grid_slots:
        grid_shots_to_display.append(None)
        grid_shot_types_to_display.append("empty")

    # Display the film strip grid
    for row_index in range(FILM_STRIP_ROWS):
        grid_cols = st.columns(FILM_STRIP_COLS)
        for col_index in range(FILM_STRIP_COLS):
            current_grid_slot_index = row_index * FILM_STRIP_COLS + col_index
            shot_buffer_in_grid = grid_shots_to_display[current_grid_slot_index]
            shot_status_in_grid = grid_shot_types_to_display[current_grid_slot_index]

            with grid_cols[col_index]:
                if shot_status_in_grid == "empty":
                    st.markdown(
                        "<div class='empty-film-slot'>Empty</div>",
                        unsafe_allow_html=True,
                    )
                elif shot_status_in_grid == "uploaded":
                    shot_buffer_in_grid.seek(0)
                    st.markdown(
                        "<div class='uploaded-indicator-wrapper'>",
                        unsafe_allow_html=True,
                    )
                    st.image(shot_buffer_in_grid, use_container_width=True)
                    st.markdown(
                        "<div class='uploaded-bar'>Uploaded</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("</div>", unsafe_allow_html=True)
                elif shot_status_in_grid == "pending":
                    shot_buffer_in_grid.seek(0)
                    st.image(shot_buffer_in_grid, use_container_width=True)
                    # Checkbox only for actual pending shots, index relative to their position in pending_camera_shots
                    if current_grid_slot_index < num_pending_shots_on_strip:
                        st.checkbox(
                            "",
                            key=f"sel_pending_shot_{current_grid_slot_index}",
                            label_visibility="collapsed",
                        )
    st.divider()

    # Action buttons for pending shots on the film strip
    upload_button_col, delete_button_col = st.columns(2)
    with upload_button_col:
        if st.button(
            "📤 Upload Selected Pending Shots",
            key="btn_film_strip_upload_action",
            use_container_width=True,
            type="primary",
        ):
            if not ss.get("event_code"):
                st.error("⚠️ Please select an event code first before uploading!")
            else:
                # Get indices of selected pending shots (indices are relative to the pending_camera_shots list)
                selected_shot_indices = [
                    idx
                    for idx in range(num_pending_shots_on_strip)
                    if ss.get(f"sel_pending_shot_{idx}", False)
                ]
                if not selected_shot_indices:
                    st.warning(
                        "No pending shots selected from the film strip for upload."
                    )
                else:
                    with st.spinner("Uploading selected shots from film strip..."):
                        successful_film_uploads, failed_film_upload_details = 0, []
                        # Iterate in reverse to correctly pop from pending_camera_shots
                        for original_pending_idx in sorted(
                            selected_shot_indices, reverse=True
                        ):
                            try:
                                shot_to_upload_buffer = ss.pending_camera_shots[
                                    original_pending_idx
                                ]
                                shot_to_upload_buffer.seek(0)

                                result_msg, was_successful = upload_image(
                                    ss.event_code, shot_to_upload_buffer
                                )

                                if was_successful:
                                    successful_film_uploads += 1
                                    # Move shot from pending to uploaded list
                                    ss.uploaded_camera_shots.insert(
                                        0,
                                        ss.pending_camera_shots.pop(
                                            original_pending_idx
                                        ),
                                    )
                                    # Clean up selection state for the checkbox
                                    if f"sel_pending_shot_{original_pending_idx}" in ss:
                                        del ss[
                                            f"sel_pending_shot_{original_pending_idx}"
                                        ]
                                else:
                                    failed_film_upload_details.append(
                                        f"Shot (original pos {original_pending_idx+1}): {result_msg}"
                                    )
                            except Exception as e:
                                failed_film_upload_details.append(
                                    f"Shot (original pos {original_pending_idx+1}): Critical error - {e}"
                                )

                        if successful_film_uploads > 0:
                            st.toast(
                                f"✅ Uploaded {successful_film_uploads} shot(s) from film strip!",
                                icon="🚀",
                            )
                        if failed_film_upload_details:
                            st.error(
                                f"❌ Failed to upload {len(failed_film_upload_details)} shot(s) from film strip:"
                            )
                            for err_detail in failed_film_upload_details:
                                st.caption(f" - {err_detail}")

                        # Rerun if any uploads happened or failed, to update the UI
                        if successful_film_uploads > 0 or failed_film_upload_details:
                            st.rerun()
    with delete_button_col:
        if st.button(
            "🗑️ Delete Selected Pending Shots",
            key="btn_film_strip_delete_action",
            use_container_width=True,
            type="secondary",
        ):
            selected_shot_indices_for_del = [
                idx
                for idx in range(num_pending_shots_on_strip)
                if ss.get(f"sel_pending_shot_{idx}", False)
            ]
            if not selected_shot_indices_for_del:
                st.warning(
                    "No pending shots selected from the film strip for deletion."
                )
            else:
                for original_pending_idx in sorted(
                    selected_shot_indices_for_del, reverse=True
                ):
                    try:
                        ss.pending_camera_shots.pop(original_pending_idx)
                        if f"sel_pending_shot_{original_pending_idx}" in ss:
                            del ss[f"sel_pending_shot_{original_pending_idx}"]
                    except IndexError:
                        st.error(
                            f"Error deleting shot at index {original_pending_idx}. List may have changed."
                        )  # Should be rare

                st.toast(
                    f"🗑️ Deleted {len(selected_shot_indices_for_del)} pending shot(s).",
                    icon="♻️",
                )
                st.rerun()  # Rerun to update film strip and counts

# --- Page Styles ---
# Includes CSS for hiding the camera's "Clear photo" button by default.
# Remove `button[title="Clear photo"] { display: none !important; }` if you want that button visible.
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
