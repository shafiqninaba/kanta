import os
from datetime import datetime  # For type hinting
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st

# API Configuration, adjust if your backend API is on a different URL
API_BASE_URL = os.getenv("BACKEND_SERVER_URL", "http://backend:8000")


# Helper to construct full API URLs
def _get_full_url(endpoint: str) -> str:
    # If API_BASE_URL already includes /api/v1 or similar, adjust accordingly
    # Example: if API_BASE_URL = "http://backend:8000" and endpoints are under /api/v1/events
    # then it should be f"{API_BASE_URL}/api/v1{endpoint}"
    # For now, assuming API_BASE_URL is the direct base for the endpoint path.
    return f"{API_BASE_URL}{endpoint}"


def get_events(event_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch all available events from the API
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/events?event_code={event_code}"
            if event_code
            else f"{API_BASE_URL}/events",
            timeout=10,
        )
        if response.status_code == 200:
            return response.json().get("events", [])
        else:
            st.error(f"Error fetching events: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"API connection error: {str(e)}")
        return []


class ApiError(Exception):
    """
    Exception raised for API request errors.
    """

    pass


def api_request(method: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an HTTP request to the API and return the parsed JSON.

    Args:
        method: HTTP method (e.g., 'GET', 'POST', 'PUT').
        endpoint: API path (e.g., '/events').
        payload: JSON payload for POST/PUT or query params for GET.

    Returns:
        A dict of the JSON response.

    Raises:
        ApiError: If the request fails or returns a non-2xx status.
    """
    url = _get_full_url(endpoint)
    try:
        response = requests.request(method, url, json=payload, timeout=10)
        data = response.json()
    except requests.RequestException as err:
        raise ApiError(f"Connection error: {err}")
    except ValueError:
        raise ApiError(f"Invalid JSON response: {response.text}")

    if not response.ok:
        detail = data.get("detail", response.text)
        raise ApiError(f"{method} {endpoint} failed ({response.status_code}): {detail}")
    return data


def create_event_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new event via the API.

    Args:
        payload: Payload with keys 'event_code', 'name', 'description', 'start_date_time', 'end_date_time'.

    Returns:
        The created event data.

    Raises:
        ApiError: If the creation fails.
    """
    return api_request("POST", "/events", payload)


def update_event_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing event via the API.

    Args:
        payload: Payload containing at least 'event_code', plus any fields to update.

    Returns:
        The updated event data.

    Raises:
        ApiError: If the update fails.
    """
    return api_request("PUT", "/events", payload)


def upload_image(event_code: str, image_file):
    """
    Upload an image to the API
    """
    try:
        files = {"image": (image_file.name, image_file, "image/jpeg")}
        response = requests.post(
            f"{API_BASE_URL}/pics?event_code={event_code}", files=files
        )

        if response.status_code == 201:
            return response.json(), True
        else:
            return (
                f"Error uploading image: {response.status_code} - {response.text}",
                False,
            )
    except Exception as e:
        return f"API connection error: {str(e)}", False


def get_images(event_code: str, limit: int = 50, offset: int = 0, **filter_params):
    """
    Fetch images from the API with optional filters
    """
    try:
        # Build query parameters
        params = {
            "event_code": event_code,
            "limit": limit,
            "offset": offset,
            **{k: v for k, v in filter_params.items() if v is not None},
        }

        response = requests.get(f"{API_BASE_URL}/pics", params=params)

        if response.status_code == 200:
            return response.json(), True
        else:
            return (
                f"Error fetching images: {response.status_code} - {response.text}",
                False,
            )
    except Exception as e:
        return f"API connection error: {str(e)}", False


def get_image_detail(image_uuid: str):
    """
    Fetch detailed information about a specific image
    """
    try:
        response = requests.get(f"{API_BASE_URL}/pics/{image_uuid}")

        if response.status_code == 200:
            return response.json(), True
        else:
            return f"Error fetching image details: {response.status_code}", False
    except Exception as e:
        return f"API connection error: {str(e)}", False


def get_clusters(event_code: str, sample_size: int = 5):
    """
    Fetch cluster information for an event
    """
    try:
        params = {"event_code": event_code, "sample_size": sample_size}

        response = requests.get(f"{API_BASE_URL}/clusters", params=params)

        if response.status_code == 200:
            return response.json(), True
        else:
            return (
                f"Error fetching clusters: {response.status_code} - {response.text}",
                False,
            )
    except Exception as e:
        return f"API connection error: {str(e)}", False


def find_similar_faces_api(
    event_code: str,
    image_file_bytes: bytes,  # Pass the raw bytes of the image
    image_filename: str,  # Filename for backend processing/logging
    metric: str = "cosine",
    top_k: int = 10,
) -> Tuple[Optional[List[Dict[str, Any]]], bool, Optional[str]]:
    """
    Find similar faces by uploading an image to the API.
    Returns (list_of_similar_face_dicts OR None, success_boolean, error_message_str OR None)
    """
    endpoint = "/find-similar"  # Corrected endpoint based on your router
    params = {
        "event_code": event_code,
        "metric": metric,
        "top_k": top_k,
    }
    # The 'image' needs to be sent as a file in a multipart/form-data request
    files = {
        "image": (image_filename, image_file_bytes, "image/jpeg")
    }  # Assuming jpeg, adjust if needed or detect

    try:
        # print(f"DEBUG: Calling find_similar_faces_api. Params: {params}, Files: {image_filename}")
        response = requests.post(
            _get_full_url(endpoint), params=params, files=files, timeout=30
        )  # Increased timeout for potential processing

        if response.status_code == 200:
            return (
                response.json(),
                True,
                None,
            )  # API returns List[SimilarFaceOut] directly
        else:
            try:
                detail = response.json().get("detail", response.text)
            except requests.exceptions.JSONDecodeError:
                detail = response.text
            err_msg = f"Error finding similar faces ({response.status_code}): {detail}"
            print(err_msg)
            return None, False, err_msg
    except requests.exceptions.RequestException as e:
        err_msg = f"API connection error for similarity search: {e}"
        print(err_msg)
        return None, False, err_msg
    except Exception as e:
        err_msg = f"An unexpected error occurred during similarity search: {e}"
        print(err_msg)
        return None, False, err_msg
