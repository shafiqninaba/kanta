import streamlit as st
from utils.session import get_event_selection, init_session_state

st.set_page_config(
    page_title="Kanta | Collaborative Event Photos",
    page_icon="📸",
    layout="wide",
)


def render_step(step: dict):
    """Render one instruction step with fixed-size image + text in two columns."""
    col_img, col_txt = st.columns([2, 3])
    with col_img:
        # Image with forced width and height
        st.image(
            step["image_src"],
            width=300,
            clamp=False,
            use_container_width=False,
            caption=step["caption"],
        )
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
            "image_src": "https://spotme.com/wp-content/uploads/2020/07/Hero-1.jpg",
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
            "image_src": "https://www.brides.com/thmb/0tBulsrYZMzz0Kwt0XcrwpQXMw4=/1500x0/filters:no_upscale():max_bytes(150000):strip_icc()/__opt__aboutcom__coeus__resources__content_migration__brides__public__brides-services__production__2016__10__24__580e5ab70480c831a105ddd8_blogs-aisle-say-guide-to-posting-wedding-pictures-post-wedding-d450714d1b614d009ca6ddf15d5800b8.jpeg",
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
            "image_src": "https://photos.smugmug.com/BLOG/Blog-images/i-4DzMFWZ/0/NCg78ZfVGwLThZt3BVVJkBNq7VgL2LmzdVTHmXfnd/XL/%40RobHammPhoto%20%236%28c%292017RobertHamm-XL.jpg",
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
            "image_src": "https://production-rhino-website-crm.s3.ap-southeast-1.amazonaws.com/Face_Recognition_17a30dc38b.png",
            "caption": "People & Similarity",
        },
    ]

    for step in steps:
        render_step(step)
        st.divider()

    st.caption("Kanta: Capturing memories, together.")


if __name__ == "__main__":
    main()
