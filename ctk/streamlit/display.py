import streamlit as st
from PIL import Image
import pandas as pd
import altair as alt
import logging
import os

logger = logging.getLogger(__name__)

def display_books_tab(filtered_df: pd.DataFrame, cover_images: dict, ebook_files: dict):
    """
    Displays the Books tab with book entries and download/view links.
    """
    total_size = len(filtered_df)
    st.subheader(f"📚 Book Entries (Total: {total_size})")
    if not filtered_df.empty:
        for idx, row in filtered_df.iterrows():
            with st.expander(f"**{row.get('title', 'No Title')}**"):
                # Layout: Cover Image & Downloads | Metadata
                cols = st.columns([1.5, 3])

                # Left Column: Cover Image
                with cols[0]:
                    # Cover Image
                    cover_path = row.get("cover_path", "")
                    cover_filename = os.path.basename(cover_path)
                    cover_data = cover_images.get(cover_filename)
                    if cover_data:
                        try:
                            image = Image.open(cover_data)
                            st.image(image, use_container_width=True, caption="🖼️ Cover")
                            logger.debug(f"Displayed cover image: {cover_filename}")
                        except Exception as e:
                            st.error(f"🖼️ Error loading image: {e}")
                            logger.error(f"Error loading image {cover_filename}: {e}")
                    else:
                        st.info("🖼️ No cover image available.")
                        logger.debug(f"No cover image available for {cover_filename}.")

                # Right Column: Metadata Details and Ebook Links
                with cols[1]:


                    # show title in a header style
                    title = row.get("title", "No Title")
                    st.markdown(f"# 📖 {title}")

                    metadata_details = {
                        "👤 **Author(s)**": ", ".join(row.get("creators", ["N/A"])),
                        "📚 **Subjects**": ", ".join(row.get("subjects", ["N/A"])),
                        "📝 **Description**": row.get("description", "N/A"),
                        "🌐 **Language**": row.get("language", "N/A"),
                        "📅 **Publication Date**": row.get("date", "N/A") if pd.notna(row.get("date", None)) else "N/A",
                        "📖 **Publisher**": row.get("publisher", "N/A"),
                        "📏 **File Size**": row.get("file_size", "N/A"),
                        "📚 **Virtual Libraries**": ", ".join(row.get("virtual_libs", ["N/A"])),
                        "🔑 **Identifiers**": ", ".join([f"{k}: {v}" for k, v in row.get("identifiers", {}).items()]),
                        "🔑 **Unique ID**": row.get("unique_id", "NA"),
                    }

                    for key, value in metadata_details.items():
                        st.markdown(f"{key}: {value}")

                    # Ebook Download and View Links
                    ebook_paths = row.get("file_paths", [])
                    if ebook_paths:
                        st.markdown("### 📥 Ebook Links")
                        for ebook_path in ebook_paths:
                            ebook_filename = os.path.basename(ebook_path)
                            ebook_data = ebook_files.get(ebook_filename)
                            if ebook_data:
                                # Determine MIME type based on file extension
                                _, ext = os.path.splitext(ebook_filename.lower())
                                mime_types = {
                                    '.pdf': 'application/pdf',
                                    '.epub': 'application/epub+zip',
                                    '.mobi': 'application/x-mobipocket-ebook',
                                    '.azw3': 'application/vnd.amazon.ebook',
                                    '.txt': 'text/plain'
                                }
                                mime_type = mime_types.get(ext, 'application/octet-stream')

                                st.download_button(
                                    label=f"💾 Download {ebook_filename}",
                                    data=ebook_data.getvalue(),
                                    file_name=ebook_filename,
                                    mime=mime_type
                                )
                                logger.debug(f"Provided link for {ebook_filename}.")
                            else:
                                st.warning(f"Ebook file '{ebook_filename}' not found in the uploaded ZIP.")
                                logger.warning(f"Ebook file '{ebook_filename}' not found in the uploaded ZIP.")
                    else:
                        st.info("📄 No ebook files available for download.")
                        logger.debug("No ebook files available for download.")
    else:
        st.info("📚 No books match the current filter criteria.")
        logger.debug("No books match the current filter criteria.")

def display_statistics_tab(filtered_df: pd.DataFrame):
    """
    Displays the Statistics tab with various visualizations.
    """
    st.subheader("📊 Statistics")

    if not filtered_df.empty:
        # Visualization: Books per Author (Top 10)
        st.markdown("### 📈 Top 10 Authors by Number of Books")
        author_counts = pd.Series([creator for creators in filtered_df['creators'] for creator in creators]).value_counts().nlargest(10).reset_index()
        author_counts.columns = ['Author', 'Number of Books']
        
        chart = alt.Chart(author_counts).mark_bar().encode(
            x=alt.X('Number of Books:Q', title='Number of Books'),
            y=alt.Y('Author:N', sort='-x', title='Author'),
            tooltip=['Author', 'Number of Books']
        ).properties(
            width=600,
            height=400
        )
        
        st.altair_chart(chart, use_container_width=True)
        logger.debug("Displayed Top 10 Authors chart.")

        # Visualization: Books per Subject (Top 10)
        st.markdown("### 📊 Top 10 Subjects by Number of Books")
        subject_counts = pd.Series([subject for subjects in filtered_df['subjects'] for subject in subjects]).value_counts().nlargest(10).reset_index()
        subject_counts.columns = ['Subject', 'Number of Books']
        
        subject_chart = alt.Chart(subject_counts).mark_bar().encode(
            x=alt.X('Number of Books:Q', title='Number of Books'),
            y=alt.Y('Subject:N', sort='-x', title='Subject'),
            tooltip=['Subject', 'Number of Books']
        ).properties(
            width=600,
            height=400
        )
        
        st.altair_chart(subject_chart, use_container_width=True)
        logger.debug("Displayed Top 10 Subjects chart.")

        # Visualization: Books Published Over Time
        st.markdown("### 📈 Books Published Over Time")
        if 'date' in filtered_df.columns and pd.api.types.is_numeric_dtype(filtered_df['date']):
            publication_years = filtered_df['date'].dropna().astype(int)
            if not publication_years.empty:
                year_counts = publication_years.value_counts().sort_index().reset_index()
                year_counts.columns = ['Year', 'Number of Books']
                
                time_chart = alt.Chart(year_counts).mark_line(point=True).encode(
                    x=alt.X('Year:O', title='Year'),
                    y=alt.Y('Number of Books:Q', title='Number of Books'),
                    tooltip=['Year', 'Number of Books']
                ).properties(
                    width=800,
                    height=400
                )
                
                st.altair_chart(time_chart, use_container_width=True)
                logger.debug("Displayed Books Published Over Time chart.")
            else:
                st.info("📅 No publication date data available.")
                logger.warning("Publication year data is empty after filtering.")
        else:
            st.info("📅 Publication date data is not available or not in a numeric format.")
            logger.warning("Publication date data is not available or not numeric.")
    else:
        st.info("📊 No statistics to display as no books match the current filter criteria.")
        logger.debug("No statistics to display due to empty filtered DataFrame.")
