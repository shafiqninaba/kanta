"""
People & Similarity Search page for Streamlit application.

Allows browsing identified people, filtering the gallery by person,
and finding similar faces via upload or camera capture.
"""

import base64
import json
import time
from io import BytesIO
from typing import Any, Dict, List, Tuple

import streamlit as st
from PIL import Image, UnidentifiedImageError
from utils.api import find_similar_faces, get_clusters
from utils.image import crop_and_encode_face, fetch_image_bytes_from_url
from utils.session import get_event_selection, init_session_state

# Page Configuration
st.set_page_config(page_title="People & Similarity", page_icon="🧑‍🤝‍🧑", layout="wide")

# --------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------
CLUSTER_ID_UNASSIGNED = -1
CLUSTER_ID_PROCESSING = -2
PERSON_CARD_COLS = 4
SAMPLE_FACE_SIZE: Tuple[int, int] = (150, 150)
SIMILAR_FACE_SIZE: Tuple[int, int] = (120, 120)
SWAP_INTERVAL_MS = 20_000

# --------------------------------------------------------------------
# Session State Initialization
# --------------------------------------------------------------------
init_session_state()
get_event_selection()
ss = st.session_state
ss.setdefault("people_sample_size", 1)
ss.setdefault("people_selected_clusters", {})
ss.setdefault("similarity_top_k", 10)
ss.setdefault("similarity_metric", "cosine")
ss.setdefault("similarity_results", None)
ss.setdefault("similarity_query_b64", None)

# --------------------------------------------------------------------
# Title and Event Validation
# --------------------------------------------------------------------
st.title("🧑‍🤝‍🧑 People & Similarity Search")
if not ss.get("event_code"):
    st.warning("👈 Select an event from the sidebar first.")
    st.stop()

# --------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------
tab_people, tab_similarity = st.tabs(["👥 Identified People", "🔍 Find Similar Faces"])

# =================================
# TAB 1: IDENTIFIED PEOPLE
# =================================
with tab_people:
    st.markdown("Select individuals below to filter the gallery by person.")

    # Sample-size slider
    new_size = st.slider(
        "Sample faces per person",
        min_value=1,
        max_value=10,
        value=ss.people_sample_size,
        key="people_sample_size_slider",
    )
    if new_size != ss.people_sample_size:
        ss.people_sample_size = new_size
        ss.people_selected_clusters.clear()

    st.markdown("---")

    # Fetch clusters
    with st.spinner(f"Loading {ss.people_sample_size} samples per person..."):
        clusters = get_clusters(ss.event_code, ss.people_sample_size)

    if not clusters:
        st.info("No identified people data available.")
    else:
        persons = [c for c in clusters if c.get("cluster_id", -3) >= 0]
        unassigned = next(
            (c for c in clusters if c.get("cluster_id") == CLUSTER_ID_UNASSIGNED), None
        )
        processing = next(
            (c for c in clusters if c.get("cluster_id") == CLUSTER_ID_PROCESSING), None
        )

        # Build display cards
        cards: List[Dict[str, Any]] = []
        for idx, cl in enumerate(persons):
            cid = cl["cluster_id"]
            count = cl.get("face_count", 0)
            samples = cl.get("samples", [])
            urls: List[str] = []
            for sm in samples:
                data = fetch_image_bytes_from_url(sm.get("sample_blob_url"))
                if data:
                    b64 = crop_and_encode_face(
                        data, sm.get("sample_bbox", {}), SAMPLE_FACE_SIZE
                    )
                    if b64:
                        urls.append(b64)
            initial = urls[0] if urls else "https://via.placeholder.com/150"
            cards.append(
                {
                    "cluster_id": cid,
                    "count": count,
                    "urls": urls,
                    "initial": initial,
                    "js_id": f"person_{cid}_{idx}",
                }
            )

        if not cards:
            st.info("No identified people to display.")
        else:
            cols = st.columns(PERSON_CARD_COLS)
            for i, card in enumerate(cards):
                with cols[i % PERSON_CARD_COLS]:
                    cid = card["cluster_id"]
                    key = f"select_person_{cid}"
                    selected = st.checkbox(
                        f"Person {cid}",
                        value=ss.people_selected_clusters.get(cid, False),
                        key=key,
                    )
                    ss.people_selected_clusters[cid] = selected
                    border = "3px solid #007bff" if selected else "3px solid #f0f2f6"
                    html = f"""
<div style='border:{border};border-radius:8px;display:flex;flex-direction:column;align-items:center;padding:8px;'>
  <img id='{card['js_id']}' src='{card['initial']}' style='width:150px;height:150px;border-radius:50%;margin-bottom:8px;'>
  <div style='text-align:center;font-size:0.9em;'>Person {cid} ({card['count']})</div>
</div>
<script>
if (!document.getElementById('{card['js_id']}').dataset.swapping) {{
  let arr = {json.dumps(card['urls'])};
  let idx=0; let el=document.getElementById('{card['js_id']}');
  if(arr.length>1) setInterval(()=>{{ idx=(idx+1)%arr.length; el.src=arr[idx]; }}, {SWAP_INTERVAL_MS});
  el.dataset.swapping='true';
}}
</script>"""
                    st.markdown(html, unsafe_allow_html=True)

            sel_ids = [cid for cid, sel in ss.people_selected_clusters.items() if sel]
            if st.button(
                f"🖼️ View Images of {len(sel_ids)} People",
                key="view_selected_people",
                disabled=not sel_ids,
                type="primary",
                use_container_width=True,
            ):
                ss.gallery_filter_clusters = sel_ids
                ss.gallery_page = 1
                st.switch_page("pages/03_Gallery.py")

        # Unassigned
        if unassigned and unassigned.get("face_count", 0) > 0:
            st.markdown("---")
            st.subheader(f"Unidentified: {unassigned['face_count']}")
            with st.expander("View samples of unidentified faces", expanded=False):
                urls_un = []
                for sm in unassigned.get("samples", []):
                    data = fetch_image_bytes_from_url(sm.get("sample_blob_url"))
                    if data:
                        b64 = crop_and_encode_face(
                            data, sm.get("sample_bbox", {}), (80, 80)
                        )
                        if b64:
                            urls_un.append(b64)
                if urls_un:
                    cols_u = st.columns(min(8, len(urls_un)))
                    for j, u in enumerate(urls_un):
                        cols_u[j % len(cols_u)].image(u, width=80)
                else:
                    st.write("No samples available.")

        # Processing indicator
        if processing and processing.get("face_count", 0) > 0:
            st.info(f"⚙️ Processing {processing['face_count']} faces...")

# =================================
# TAB 2: SIMILARITY SEARCH
# =================================
with tab_similarity:
    st.subheader("🔍 Find Similar Faces")
    st.markdown("Upload or take a photo to search for similar faces.")

    # Inputs and settings
    col_input, col_controls = st.columns([1, 1])
    with col_input:
        uploaded = st.file_uploader(
            "Upload face image",
            type=["jpg", "jpeg", "png"],
            key="sim_uploader",
            accept_multiple_files=False,
        )
        snapped = st.camera_input("Or take a photo", key="sim_camera")
        query = uploaded or snapped

    with col_controls:
        ss.similarity_top_k = st.number_input(
            "Top K",
            min_value=1,
            max_value=50,
            value=ss.similarity_top_k,
            key="sim_topk",
        )
        ss.similarity_metric = st.selectbox(
            "Metric",
            ["cosine", "l2"],
            index=["cosine", "l2"].index(ss.similarity_metric),
            key="sim_metric",
        )
        search_disabled = query is None
        if st.button(
            "🔍 Search",
            key="sim_search",
            disabled=search_disabled,
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Searching for similar faces..."):
                results = (
                    find_similar_faces(
                        ss.event_code,
                        query.getvalue(),
                        query.name if hasattr(query, "name") else "uploaded.jpg",
                        ss.similarity_metric,
                        ss.similarity_top_k,
                    )
                    or []
                )
                ss.similarity_results = results

    st.markdown("---")

    # Display query image and results side-by-side
    if query:
        try:
            img = Image.open(query).convert("RGB")
            img.thumbnail((200, 200))
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            q_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            q_b64 = None

        col_q, col_r = st.columns([1, 2])
        with col_q:
            if q_b64:
                st.image(
                    f"data:image/png;base64,{q_b64}",
                    caption="Query Image",
                    use_column_width=True,
                )
        with col_r:
            if ss.similarity_results is None:
                st.info("No results yet.")
            elif not ss.similarity_results:
                st.info("No similar faces found.")
            else:
                st.subheader(f"Top {len(ss.similarity_results)} Similar Faces")
                for res in ss.similarity_results:
                    b64 = None
                    data = fetch_image_bytes_from_url(res.get("azure_blob_url"))
                    if data:
                        b64 = crop_and_encode_face(
                            data, res.get("bbox", {}), SIMILAR_FACE_SIZE
                        )
                    if b64:
                        st.image(b64, width=SIMILAR_FACE_SIZE[0])
                    else:
                        st.markdown(
                            f"<div class='similar-face-placeholder'>"
                            f"ID:{res.get('cluster_id')}<br/>Dist:{res.get('distance'):.2f}</div>",
                            unsafe_allow_html=True,
                        )
                    st.caption(
                        f"Person ID: {res.get('cluster_id')} | Distance: {res.get('distance'):.2f}"
                    )
                    st.divider()

# --------------------------------------------------------------------
# Custom CSS
# --------------------------------------------------------------------
st.markdown(
    f"""
<style>
.similar-face-placeholder {{
  width:{SIMILAR_FACE_SIZE[0]}px;
  height:{SIMILAR_FACE_SIZE[1]}px;
  border-radius:50%;
  background:#e0e0e0;
  display:flex;
  justify-content:center;
  align-items:center;
  text-align:center;
  margin:auto 0;
}}
</style>
""",
    unsafe_allow_html=True,
)
