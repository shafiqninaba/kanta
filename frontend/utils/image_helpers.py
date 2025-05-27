# utils/image_helpers.py

import streamlit as st  # For st.sidebar.error in fetch_image_bytes_from_url
import requests
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import base64


@st.cache_data(ttl=3600)  # Keep caching here as it's data fetching
def fetch_image_bytes_from_url(image_url: str) -> BytesIO | None:
    """Fetches image bytes from a URL. Cached for 1 hour."""
    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        return BytesIO(response.content)
    except requests.exceptions.RequestException as e:
        # Using st.sidebar.error might be problematic if this util is used
        # in non-Streamlit contexts or before sidebar is fully available.
        # Consider just printing or logging, or making error display conditional.
        # For now, keeping it, but be mindful.
        st.sidebar.error(f"Error fetching image (see console): {image_url[:50]}...")
        print(f"Error fetching image data from {image_url[:60]}...: {e}")
        return None


def crop_and_encode_face(
    full_image_bytes_io: BytesIO,
    bbox: dict,
    target_size: tuple,
    padding_w_factor: float = 0.3,  # Default padding factor for width
    padding_h_factor: float = 0.3,  # Default padding factor for height
) -> str | None:
    """
    Crops a face from an image, resizes with padding, and returns as base64 data URL.
    padding_w_factor and padding_h_factor are percentages of the bbox width/height.
    """
    try:
        img = Image.open(full_image_bytes_io)
        x, y, w, h = (
            int(bbox["x"]),
            int(bbox["y"]),
            int(bbox["width"]),
            int(bbox["height"]),
        )

        # Calculate padding in pixels based on factors
        pad_w_px = int(w * padding_w_factor)
        pad_h_px = int(h * padding_h_factor)

        crop_box = (
            max(0, x - pad_w_px),
            max(0, y - pad_h_px),
            min(img.width, x + w + pad_w_px),
            min(img.height, y + h + pad_h_px),
        )
        face_img = img.crop(crop_box)

        if face_img.width == 0 or face_img.height == 0:
            print(f"Warning: Cropped image has zero dimension for bbox {bbox}")
            return None  # Avoid error with thumbnailing zero-size image

        face_img.thumbnail(target_size, Image.Resampling.LANCZOS)

        # Create a canvas and paste the (potentially smaller) thumbnail onto it
        # to ensure the final image is exactly target_size, letterboxed if necessary.
        canvas = Image.new("RGB", target_size, (255, 255, 255))  # White background
        paste_x = (target_size[0] - face_img.width) // 2
        paste_y = (target_size[1] - face_img.height) // 2
        canvas.paste(face_img, (paste_x, paste_y))

        buffered = BytesIO()
        canvas.save(buffered, format="PNG")  # PNG supports transparency if needed later
        base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{base64_str}"
    except UnidentifiedImageError:
        print(f"Error: Could not identify image for bbox {bbox} during face cropping.")
    except Exception as e:
        print(f"Error cropping/encoding face with bbox {bbox}: {e}")
    return None
