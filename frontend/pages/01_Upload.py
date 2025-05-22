import streamlit as st
from PIL import Image
from utils.api import upload_image
from utils.session import init_session_state, get_event_selection

# Initialize session and sidebar
init_session_state()
get_event_selection()

st.title("📤 Upload Images")

# Check if event is selected
if not st.session_state.event_code:
    st.warning("Please select an event from the sidebar to continue.")
    st.stop()

# Image upload widget
uploaded_file = st.file_uploader("Choose an image", type=['jpg', 'jpeg', 'png'])

if uploaded_file is not None:
    # Preview the image
    img = Image.open(uploaded_file)
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(img, caption="Preview", use_column_width=True)
    
    with col2:
        st.info("Ready to upload")
        
    # Reset file pointer for upload
    uploaded_file.seek(0)
    
    # Upload button
    if st.button("Upload Image"):
        with st.spinner("Uploading..."):
            result, success = upload_image(st.session_state.event_code, uploaded_file)
            
            if success:
                st.success("Image uploaded successfully!")
                st.json(result)
            else:
                st.error(result)