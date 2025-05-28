import streamlit as st
from utils.session import get_event_selection, init_session_state

st.set_page_config(
    page_title="Kanta | Collaborative Event Photos",
    page_icon="📸",
    layout="wide",
)


def render_step(step: dict):
    """Render one instruction step with image + text in two columns."""
    col_img, col_txt = st.columns([2, 3])
    with col_img:
        # TODO: replace `image_src` with your own screenshot/GIF URL or local path
        st.image(step["image_src"], width=300, caption=step["caption"])
    with col_txt:
        st.subheader(step["title"])
        st.write(step["description"])
        st.page_link(
            page=step["page"],
            label=step["link_label"],
            icon=step["icon"],
            use_container_width=True,
        )


def main():
    # init
    init_session_state()
    get_event_selection()

    # header
    st.title("Kanta | Collaborative Event Photos")
    st.markdown(
        "_A collaborative film camera app for events, with built-in face detection and "
        "automatic photo organization._"
    )
    st.markdown(
        "#### /kæntæ/  –  _ meaning ‘lens’ in Malay_\n"
        "Kanta lets event participants capture, share, and organize photos in a shared "
        "digital camera roll, automatically grouping moments by person."
    )
    st.divider()

    # instruction steps
    st.markdown("## How to Use Kanta")
    steps = [
        {
            "title": "1. Event Setup (Admin)",
            "description": "Create or manage events, and generate a unique Event Code.",
            "page": "pages/01_Events.py",
            "link_label": "Go to Event Management ›",
            "icon": "🗂",
            "image_src": "https://via.placeholder.com/300x200?text=Event+Setup",
            "caption": "Event Management",
        },
        {
            "title": "2. Capture & Upload",
            "description": (
                "Share your Event Code or use the Camera & Upload page to collect "
                "photos in real time."
            ),
            "page": "pages/02_Camera.py",
            "link_label": "Go to Camera & Upload ›",
            "icon": "📷",
            "image_src": "https://via.placeholder.com/300x200?text=Capture+%26+Upload",
            "caption": "Camera & Upload",
        },
        {
            "title": "3. Browse Gallery",
            "description": (
                "Filter by date, faces, or specific people. Download individual photos or batches."
            ),
            "page": "pages/03_Gallery.py",
            "link_label": "Go to Image Gallery ›",
            "icon": "🖼️",
            "image_src": "https://via.placeholder.com/300x200?text=Image+Gallery",
            "caption": "Image Gallery",
        },
        {
            "title": "4. Discover People",
            "description": (
                "Explore auto-detected faces, view all photos of someone, or search by example image."
            ),
            "page": "pages/04_People.py",
            "link_label": "Go to People Discovery ›",
            "icon": "👥",
            "image_src": "https://via.placeholder.com/300x200?text=People+%26+Similarity",
            "caption": "People & Similarity",
        },
    ]

    for step in steps:
        render_step(step)
        st.divider()

    st.caption("Kanta: Capturing memories, together.")


if __name__ == "__main__":
    main()
