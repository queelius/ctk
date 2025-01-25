import streamlit as st
import pandas as pd
import os
import logging
from utils import load_metadata, extract_zip
from filters import sanitize_dataframe, create_filters
from display import display_conversation_tab, display_statistics_tab

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def display_dashboard(convs: list):
    """
    Displays the main dashboard with advanced filtering and a compact UI layout using tabs.
    """
    # Convert metadata list to DataFrame
    df = pd.DataFrame(convs)
    logger.debug("Converted metadata list to DataFrame.")

    # Sanitize DataFrame
    df = sanitize_dataframe(df)
    logger.debug("Sanitized DataFrame.")

    # Apply Filters
    filtered_df = create_filters(df)
    logger.debug("Applied filters to DataFrame.")

    # Create Tabs
    tabs = st.tabs(["📚 Conversations", "📊 Statistics", "Advanced Search", "📖 Table", "📝 Instructions"])
    

    with tabs[0]:
        pass
        # Display Books
        #display_conversation_tab(filtered_df, cover_images, ebook_files)

    with tabs[1]:
        # Display Statistics
        display_statistics_tab(filtered_df)

    with tabs[2]:
        # Display Advanced Search
        display_advanced_search_tab(convs)

    with tabs[3]:
        # Display Table
        display_table_view_tab(filtered_df)

    with tabs[4]:
        # Display Instructions
        st.header("📝 Instructions")
        st.markdown("""
        **Export** the ctk library: `ctk export <ctk-library> --output-format zip`
        **Upload** the zip file using the uploader below.
        **Interact** with the ctk library using the tabs in the main window.
        """)

    # Display Footer
    # display_footer()

def main():
    st.set_page_config(page_title="ctk Dashboard", layout="wide")
    st.title("📚 ctk Dashoard")
    st.write("""Upload a **zip** file of the ctk library.""")

    # File uploader for ZIP archive
    st.subheader("📁 Upload ZIP Archive")
    zip_file = st.file_uploader(
        label="Upload a ZIP file of your ctk library",
        type=["zip"],
        key="zip_upload"
    )

    MAX_ZIP_SIZE = 8 * 1024 * 1024 * 1024  # 1 GB

    if zip_file:
        print("Uploaded ZIP file:", zip_file.name)
        print("🔄 File size:", zip_file.size)
        if zip_file.size > MAX_ZIP_SIZE:
            st.error(f"❌ Uploaded ZIP file is {zip_file.size / 1024 / 1024 / 1024:.2f} GB, which exceeds the size limit of 1 GB.")
            logger.error("Uploaded ZIP file exceeds the size limit.")
            st.stop()

        with st.spinner("🔄 Extracting and processing ZIP archive..."):
            extracted_files = extract_zip(zip_file)
        if not extracted_files:
            logger.error("No files extracted from the ZIP archive.")
            st.stop()  # Stop if extraction failed

        import json
        with open("conversations.json", "r", encoding="utf-8") as f:
            return json.load(f)

        display_dashboard(convs)
    else:
        st.info("📥 Please upload a ZIP archive to get started.")
        logger.debug("No ZIP archive uploaded yet.")

def display_table_view_tab(filtered_df: pd.DataFrame):
    """
    Displays the Table tab with a searchable table of metadata.
    """
    st.header("📖 Table")
    st.write("Explore the conversation trees of your library using the interactive table below.")
    st.dataframe(filtered_df)

def display_advanced_search_tab(convs: list):
    """
    Using JMESPath to search the conversations. 
    """
    import jmespath

    st.header("Advanced Search")
    st.write("Use JMESPath queries to search the metadata list.")
    query = st.text_input("Enter a JMESPath query", "[].[?created > `2020-01-01`]")
    try:
        result = jmespath.search(query, convs)
        st.write("Search Results:")
        st.write(result)
    except Exception as e:
        st.error(f"An error occurred: {e}")
        logger.error(f"JMESPath search error: {e}")

if __name__ == "__main__":
    main()
