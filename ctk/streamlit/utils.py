import json
import os
import zipfile
from io import BytesIO
import streamlit as st
import streamlit as st
from typing import List, Dict

def extract_zip(zip_bytes: BytesIO) -> dict:
    """
    Extracts a ZIP file in-memory and returns a dictionary of its contents.
    Keys are file names, and values are BytesIO objects containing the file data.
    """
    extracted_files = {}
    try:
        with zipfile.ZipFile(zip_bytes) as z:
            for file_info in z.infolist():
                if not file_info.is_dir():
                    with z.open(file_info) as f:
                        normalized_path = os.path.normpath(file_info.filename)
                        # Prevent path traversal
                        if os.path.commonprefix([normalized_path, os.path.basename(normalized_path)]) != "":
                            extracted_files[normalized_path] = BytesIO(f.read())
        return extracted_files
    except zipfile.BadZipFile:
        st.error("The uploaded file is not a valid ZIP archive.")
        return {}
    except Exception as e:
        st.error(f"Error extracting ZIP file: {e}")
        return {}

