import pandas as pd
import streamlit as st
import logging

logger = logging.getLogger(__name__)

def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes the DataFrame by ensuring correct data types and handling missing values.
    """
    # List of columns that should contain lists
    list_columns = ['creators', 'subjects', 'file_paths']
    
    def ensure_list(column):
        """
        Ensures that each entry in the column is a list. If not, replaces it with an empty list.
        """
        return column.apply(lambda x: x if isinstance(x, list) else [])
    
    for col in list_columns:
        if col in df.columns:
            df[col] = ensure_list(df[col])
            logger.debug(f"Processed list column: {col}")
        else:
            df[col] = [[] for _ in range(len(df))]
            logger.debug(f"Created empty list column: {col}")
    
    # Handle 'identifiers' column
    if 'identifiers' in df.columns:
        df['identifiers'] = df['identifiers'].apply(lambda x: x if isinstance(x, dict) else {})
        logger.debug("Sanitized 'identifiers' column.")
    else:
        df['identifiers'] = [{} for _ in range(len(df))]
        logger.debug("Created empty 'identifiers' column.")
    
    # Sanitize 'language' column
    if 'language' in df.columns:
        df['language'] = df['language'].apply(lambda x: x if isinstance(x, str) else '').fillna('').astype(str)
        logger.debug("Sanitized 'language' column.")
    else:
        df['language'] = ['' for _ in range(len(df))]
        logger.debug("Created empty 'language' column.")
    
    # Sanitize 'cover_path' column
    if 'cover_path' in df.columns:
        df['cover_path'] = df['cover_path'].apply(lambda x: x if isinstance(x, str) else '').fillna('').astype(str)
        logger.debug("Sanitized 'cover_path' column.")
    else:
        df['cover_path'] = ['' for _ in range(len(df))]
        logger.debug("Created empty 'cover_path' column.")
    
    # Sanitize string fields: 'title', 'description'
    string_fields = ['title', 'description']
    for field in string_fields:
        if field in df.columns:
            df[field] = df[field].apply(lambda x: x if isinstance(x, str) else '').fillna('').astype(str)
            logger.debug(f"Sanitized '{field}' column.")
        else:
            df[field] = ['' for _ in range(len(df))]
            logger.debug(f"Created empty '{field}' column.")
    
    # Sanitize 'date' column
    if 'date' in df.columns:
        df['date'] = pd.to_numeric(df['date'], errors='coerce')
        logger.debug("Sanitized 'date' column to ensure numeric types.")
    else:
        df['date'] = [None for _ in range(len(df))]
        logger.debug("Created empty 'date' column.")
    
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
    
    # Author Filter (Multi-select)
    all_creators = sorted(set(creator for creators in df['creators'] for creator in creators))
    selected_authors = st.sidebar.multiselect("👤 Filter by Author(s)", all_creators, default=[])
    
    # Subjects Filter (Multi-select)
    all_subjects = sorted(set(subject for subjects in df['subjects'] for subject in subjects))
    selected_subjects = st.sidebar.multiselect("📚 Filter by Subject(s)", all_subjects, default=[])

    # Search by Various Libraries
    all_libraries = sorted(set(lib for libs in df['virtual_libs'] for lib in libs))
    selected_libraries = st.sidebar.multiselect("📚 Filter by Virtual Library(s)", all_libraries, default=[])
    
    # Language Filter (Multi-select)
    all_languages = sorted(set(lang for lang in df['language'] if lang))
    selected_languages = st.sidebar.multiselect("🌐 Filter by Language(s)", all_languages, default=[])
    
    # Publication Date Filter (Range Slider)
    selected_years = None
    if 'date' in df.columns and pd.api.types.is_numeric_dtype(df['date']):
        min_year = int(df['date'].min()) if pd.notna(df['date'].min()) else 0
        max_year = int(df['date'].max()) if pd.notna(df['date'].max()) else 0
        if min_year and max_year:
            selected_years = st.sidebar.slider("📅 Publication Year Range", min_year, max_year, (min_year, max_year))
            logger.debug(f"Publication year range selected: {selected_years}")
        else:
            st.sidebar.info("📅 No valid publication year data available.")
            logger.warning("Publication year data is not available or entirely NaN.")
    else:
        st.sidebar.info("📅 Publication date data is not available or not in a numeric format.")
        logger.warning("Publication date data is not available or not numeric.")
    
    # Identifier Search
    identifier_search = st.sidebar.text_input("🔑 Search by Identifier (e.g., ISBN)")
    
    # Apply Filters
    filtered_df = df.copy()
    
    if title_search:
        filtered_df = filtered_df[filtered_df['title'].str.contains(title_search, case=False, na=False)]
        logger.debug(f"Applied title search filter: '{title_search}'")
    
    if selected_authors:
        filtered_df = filtered_df[filtered_df['creators'].apply(lambda x: any(creator in selected_authors for creator in x))]
        logger.debug(f"Applied author filter: {selected_authors}")
    
    if selected_subjects:
        filtered_df = filtered_df[filtered_df['subjects'].apply(lambda x: any(subject in selected_subjects for subject in x))]
        logger.debug(f"Applied subject filter: {selected_subjects}")

    if selected_libraries:
        filtered_df = filtered_df[filtered_df['virtual_libs'].apply(lambda x: any(lib in selected_libraries for lib in x))]
        logger.debug(f"Applied library filter: {selected_libraries}")
    
    if selected_languages:
        filtered_df = filtered_df[filtered_df['language'].isin(selected_languages)]
        logger.debug(f"Applied language filter: {selected_languages}")
    
    if selected_years:
        filtered_df = filtered_df[(filtered_df['date'] >= selected_years[0]) & (filtered_df['date'] <= selected_years[1])]
        logger.debug(f"Applied publication year range filter: {selected_years}")
    
    if identifier_search:
        idents = filtered_df['identifiers']
        idents_stringified = idents.apply(
            lambda x: ' '.join(f"{k}:{v}" for k, v in x.items()) if isinstance(x, dict) else str(x)
        )
        filtered_df = filtered_df[idents_stringified.str.contains(identifier_search)]
    
    return filtered_df
