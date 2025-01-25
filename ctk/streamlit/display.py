import streamlit as st
from PIL import Image
import pandas as pd
import altair as alt
import logging
import os

logger = logging.getLogger(__name__)

def display_conversation_tab(filtered_df: pd.DataFrame):
    """
    Displays the Books tab with book entries and download/view links.
    """
    total_size = len(filtered_df)
    st.subheader(f"📚 Conversations (Total: {total_size})")
    if not filtered_df.empty:
        for idx, row in filtered_df.iterrows():
            with st.expander(f"**{row.get('title', 'No Title')}**"):
                # show title in a header style
                title = row.get("title", "No Title")
                st.markdown(f"# 📖 {title}")

                metadata_details = {
                    "🔑 **Unique ID**": row.get("id", "NA"),
                }

                for key, value in metadata_details.items():
                    st.markdown(f"{key}: {value}")

                else:
                    st.info("📄 No conversation trees.")
                    logger.debug("No conversation trees.")
    else:
        st.info("📚 No conversation trees match the current filter criteria.")
        logger.debug("No conversation trees match the current filter criteria.")
