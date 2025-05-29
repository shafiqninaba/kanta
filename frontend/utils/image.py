import base64
from io import BytesIO
from typing import Any, Dict, Optional, Tuple

import requests
from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError


def apply_filter_to_image(image: Image.Image, filter_mode: str) -> Image.Image:
    """
    Apply a visual filter to a PIL Image.

    Args:
        image: Original PIL Image.
        filter_mode: One of ['Normal', 'Black & White', 'Warm', 'Cool', 'Sepia'].

    Returns:
        A new PIL Image object with the filter applied.
    """
    if filter_mode == "Black & White":
        return image.convert("L").convert("RGB")

    if filter_mode == "Warm":
        enhancer = ImageEnhance.Color(image)
        warm_img = enhancer.enhance(1.3)
        overlay = Image.new("RGB", image.size, (255, 230, 200))
        return Image.blend(warm_img, overlay, 0.15)

    if filter_mode == "Cool":
        enhancer = ImageEnhance.Color(image)
        cool_img = enhancer.enhance(0.9)
        overlay = Image.new("RGB", image.size, (200, 230, 255))
        return Image.blend(cool_img, overlay, 0.15)

    if filter_mode == "Sepia":
        return ImageOps.colorize(image.convert("L"), black="#704214", white="#C0A080")

    return image


def fetch_image_bytes_from_url(url: str, timeout: int = 15) -> Optional[BytesIO]:
    """
    Download image data from a URL and return it as a BytesIO stream.

    Args:
        url: The web address of the image.
        timeout: Request timeout in seconds.

    Returns:
        BytesIO containing the image data, or None on failure.

    Raises:
        requests.HTTPError: On non-200 response codes.
        requests.RequestException: On network-related errors.
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return BytesIO(response.content)

    except Exception:
        raise


def crop_and_encode_face(
    full_image_stream: BytesIO,
    bbox: Dict[str, Any],
    target_size: Tuple[int, int],
    padding_w_factor: float = 0.3,
    padding_h_factor: float = 0.3,
) -> Optional[str]:
    """
    Crop a face region from an image, resize with padding, and return a base64-encoded PNG URI.

    Args:
        full_image_stream: BytesIO stream of the full image.
        bbox: Dictionary with keys 'x', 'y', 'width', 'height' specifying the face box.
        target_size: (width, height) of the output image.
        padding_w_factor: Fractional padding of bbox width on each side.
        padding_h_factor: Fractional padding of bbox height on each side.

    Returns:
        A data URL (str) containing the PNG-encoded face image, or None on error.
    """
    try:
        img = Image.open(full_image_stream)
        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        w = int(bbox.get("width", 0))
        h = int(bbox.get("height", 0))

        pad_w = int(w * padding_w_factor)
        pad_h = int(h * padding_h_factor)

        left = max(0, x - pad_w)
        top = max(0, y - pad_h)
        right = min(img.width, x + w + pad_w)
        bottom = min(img.height, y + h + pad_h)

        face = img.crop((left, top, right, bottom))
        if face.width == 0 or face.height == 0:
            return None

        face.thumbnail(target_size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", target_size, (255, 255, 255))
        paste_x = (target_size[0] - face.width) // 2
        paste_y = (target_size[1] - face.height) // 2
        canvas.paste(face, (paste_x, paste_y))

        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    except (UnidentifiedImageError, OSError):
        return None
    except Exception:
        # Let caller handle unexpected errors
        raise
