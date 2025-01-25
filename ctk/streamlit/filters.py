import pandas as pd
import streamlit as st
import logging

logger = logging.getLogger(__name__)

def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes the DataFrame by ensuring correct data types and handling missing values.
    """
    # Sanitize string fields: 'title', 'description'
    string_fields = ['title']
    for field in string_fields:
        df[field] = df[field].apply(lambda x: x if isinstance(x, str) else '').fillna('').astype(str)
    
    df['created'] = pd.to_numeric(df['date'], errors='coerce')
    return df

def create_filters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Creates and applies advanced filters to the DataFrame based on user inputs.
    Returns the filtered DataFrame.
    """
    # Sidebar for Filters
    st.sidebar.header("🔍 Filters")
    
    # Title Search
    title_search = st.sidebar.text_input("🔎 Search by Title")
    
    # Created Date Filter (Range Slider)
    selected_years = None
    if 'created' in df.columns and pd.api.types.is_numeric_dtype(df['created']):
        min_year = int(df['created'].min()) if pd.notna(df['created'].min()) else 0
        max_year = int(df['created'].max()) if pd.notna(df['created'].max()) else 0
        if min_year and max_year:
            selected_years = st.sidebar.slider("📅 Created Year Range", min_year, max_year, (min_year, max_year))
        else:
            st.sidebar.info("📅 No valid creation year data available.")
    else:
        st.sidebar.info("📅 Created data is not available.")
    
    # Apply Filters
    filtered_df = df.copy()
    
    if title_search:
        filtered_df = filtered_df[filtered_df['title'].str.contains(title_search, case=False, na=False)]
    
    if selected_years:
        filtered_df = filtered_df[(filtered_df['created'] >= selected_years[0]) & (filtered_df['created'] <= selected_years[1])]
    
    return filtered_df
