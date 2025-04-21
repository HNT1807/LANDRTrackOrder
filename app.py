import streamlit as st
import re
import zipfile
import io
import os

# Initialize session state
if 'sorted_file_info' not in st.session_state:
    st.session_state.sorted_file_info = [] # Stores dicts with original info + initial rename
if 'file_data_map' not in st.session_state:
    st.session_state.file_data_map = {}
if 'final_renamed_data' not in st.session_state:
    st.session_state.final_renamed_data = [] # Stores tuples of (final_filename, data)

# Function to parse filename for bpm and key
def parse_filename(filename):
    # Regex to capture base name, key, and bpm
    # Example: CBOH_Orchestral_Horror_63_keyCm_60bpm.wav
    #          <--- base ----------> <key> <bpm> <ext>
    match = re.match(r"^(.*?)_key([A-Ga-g][#b]?m?)_(\d+)bpm(\.wav)$", filename, re.IGNORECASE)
    if match:
        base_name = match.group(1)
        key = match.group(2)
        bpm = int(match.group(3))
        extension = match.group(4)
        return {"base_name": base_name, "key": key, "bpm": bpm, "extension": extension, "original_filename": filename}
    else:
        # Try a more general pattern if the first fails (e.g. different separators)
        # This looks for _key<KEY> and _<BPM>bpm anywhere before the extension
        match = re.search(r"_key([A-Ga-g][#b]?m?)", filename, re.IGNORECASE)
        key = match.group(1) if match else None

        match = re.search(r"_(\d+)bpm", filename, re.IGNORECASE)
        bpm = int(match.group(1)) if match else None

        if key is not None and bpm is not None:
             # Attempt to reconstruct base name (less reliable)
             base_name = filename.split("_key")[0] # Simplistic assumption
             extension = os.path.splitext(filename)[1]
             if extension.lower() != ".wav": # Ensure it's still a wav
                 return None
             return {"base_name": base_name, "key": key, "bpm": bpm, "extension": extension, "original_filename": filename}

        st.warning(f"Could not parse metadata (key, bpm) from filename: {filename}. Ensure it follows the pattern '..._keyKey_BPMbpm.wav'. Skipping this file.")
        return None

# Define key order based on musical pitch
def get_key_sort_value(key_str):
    # Normalize case for parsing
    key_str = key_str.lower()
    
    # Define the chromatic scale order (starting from C for simplicity in mapping)
    # Maps note name (and its enharmonic equivalent) to a sortable number.
    note_map = {
        'c': 0, 'b#': 0,
        'c#': 1, 'db': 1,
        'd': 2,
        'd#': 3, 'eb': 3,
        'e': 4, 'fb': 4, # fb is rare but possible
        'f': 5, 'e#': 5, # e# is rare
        'f#': 6, 'gb': 6,
        'g': 7,
        'g#': 8, 'ab': 8,
        'a': 9,
        'a#': 10, 'bb': 10,
        'b': 11, 'cb': 11 # cb is rare
    }

    # Basic regex to extract the note part (e.g., 'f#', 'f', 'bb') from the key string (e.g., 'f#m', 'fm', 'bb')
    match = re.match(r"^([a-g][#b]?)", key_str)
    if match:
        note = match.group(1)
        # Return the mapped value, or a high value if not found (shouldn't happen with valid keys)
        return note_map.get(note, 99) 
    else:
        # Fallback for unexpected key formats: attempt alphabetical on the whole string?
        # Or return a high value to sort them last.
        st.warning(f"Could not parse note from key: {key_str}. Sorting alphabetically as fallback.")
        return 99 # Or could return key_str for alphabetical fallback

# Function to create highlighted preview string
def create_highlighted_preview(text, start_index_1_based):
    if not text or start_index_1_based <= 0 or start_index_1_based > len(text):
        return text # Return original text if index is invalid
    start_index_0_based = start_index_1_based - 1
    # Escape potential HTML characters in the text itself
    escaped_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Construct the string with the highlighted character
    return f"{escaped_text[:start_index_0_based]}<span style='color:red; font-weight:bold;'>{escaped_text[start_index_0_based]}</span>{escaped_text[start_index_0_based+1:]}"

st.set_page_config(layout="wide")
st.title("LANDR Track Order")
st.write("Upload your WAV files. They will be sorted by BPM (slowest to fastest), then by Key starting with A.")
st.write("Filenames must follow the pattern: `Anything_keyKey_BPMbpm.wav` (e.g., `MyTrack_Loop1_keyAm_120bpm.wav`)")

uploaded_files = st.file_uploader(
    "Choose WAV files",
    accept_multiple_files=True,
    type=['wav'],
    key="file_uploader" # Add key to potentially help reset state if needed
)

# Clear previous state if new files are uploaded or files are removed
if 'prev_uploaded_files' not in st.session_state:
    st.session_state.prev_uploaded_files = []

if uploaded_files != st.session_state.prev_uploaded_files:
    st.session_state.sorted_file_info = []
    st.session_state.file_data_map = {}
    st.session_state.final_renamed_data = []
    st.session_state.prev_uploaded_files = uploaded_files
    # Reset renaming inputs if files change
    st.session_state.start_index = 1
    st.session_state.num_chars = 0


if uploaded_files:
    parsed_files = []
    uploaded_filenames_display = []

    # Process uploads only if state is clear (or first run)
    if not st.session_state.sorted_file_info:
        st.session_state.file_data_map = {}
        for uploaded_file in uploaded_files:
            uploaded_filenames_display.append(f"- {uploaded_file.name}")
            file_info = parse_filename(uploaded_file.name)
            if file_info:
                parsed_files.append(file_info)
                st.session_state.file_data_map[uploaded_file.name] = uploaded_file.getvalue()
                uploaded_filenames_display[-1] += f" (Parsed: BPM={file_info['bpm']}, Key={file_info['key']})"
            else:
                uploaded_filenames_display[-1] += f" (Could not parse)"

        if parsed_files:
            # Sort files: first by BPM (ascending), then by Key (alphabetical)
            sorted_files = sorted(parsed_files, key=lambda x: (x['bpm'], get_key_sort_value(x['key'])))

            st.session_state.sorted_file_info = [] # Clear before repopulating
            st.session_state.final_renamed_data = [] # Clear before repopulating
            for i, file_info in enumerate(sorted_files):
                index_str = f"{i + 1:02d}" # Zero-padded index (01, 02, ...)
                initial_new_filename = f"{file_info['base_name']}_{index_str}_key{file_info['key']}_{file_info['bpm']}bpm{file_info['extension']}"

                # Store detailed info including the initial rename
                file_info['initial_rename'] = initial_new_filename
                st.session_state.sorted_file_info.append(file_info)

                # Populate initial final data (will be overwritten by advanced rename)
                original_data = st.session_state.file_data_map.get(file_info['original_filename'])
                if original_data:
                    st.session_state.final_renamed_data.append((initial_new_filename, original_data))
                else:
                    st.error(f"Internal error: Could not find data for {file_info['original_filename']}")
        else:
            st.warning("No files could be parsed successfully. Ensure filenames match the required format.")
            # Clear state if no files parsed
            st.session_state.sorted_file_info = []
            st.session_state.file_data_map = {}
            st.session_state.final_renamed_data = []

    # --- Display Sections ---

    # Display Uploaded Files (Collapsible)
    with st.expander("Uploaded Files Summary"):
        if uploaded_filenames_display:
             for line in uploaded_filenames_display:
                 st.text(line)
        else: # Handle case where files were uploaded but immediately removed
             st.info("No files are currently uploaded.")

    # Display Initially Sorted/Renamed Files (Collapsible)
    if st.session_state.sorted_file_info:
        with st.expander("Sorted & Indexed Files (Initial)"):
            for i, file_info in enumerate(st.session_state.sorted_file_info):
                st.text(f"  {i+1}. {file_info['initial_rename']} (Original: {file_info['original_filename']})")

        # --- Advanced Renaming Section ---
        st.subheader("Renaming (Optional)")
        

        # Select Renaming Operation
        rename_operation = st.radio(
            "Select Operation",
            ("Remove Characters", "Add Text", "Replace Text"),
            key='rename_operation',
            horizontal=True
        )

        # --- Input fields based on operation ---
        params = {}
        if rename_operation == "Remove Characters":
            # Use columns to constrain width
            c1, c2, _ = st.columns([1, 1, 2]) # Add a spacer column
            with c1:
                params['start_index'] = st.number_input(
                    "Start position",
                    min_value=1, value=st.session_state.get('rc_start_index', 1), step=1, key='rc_start_index',
                    help="1-based index to start removal from."
                )
            with c2:
                params['num_chars'] = st.number_input(
                    "Num characters",
                    min_value=0, value=st.session_state.get('rc_num_chars', 0), step=1, key='rc_num_chars',
                    help="Number of characters to remove."
                )

        elif rename_operation == "Add Text":
            c1, c2, _ = st.columns([1, 2, 1]) # Spacer column
            with c1:
                 params['position'] = st.number_input(
                    "Position",
                    min_value=1, value=st.session_state.get('at_position', 1), step=1, key='at_position',
                    help="1-based index where text will be added."
                 )
            with c2:
                params['text_to_add'] = st.text_input(
                    "Text to add",
                    value=st.session_state.get('at_text', ""), key='at_text'
                )

        elif rename_operation == "Replace Text":
            c1, c2, c3, _ = st.columns([1, 1, 2, 1]) # Spacer column
            with c1:
                params['start_index'] = st.number_input(
                    "Start position",
                    min_value=1, value=st.session_state.get('rt_start_index', 1), step=1, key='rt_start_index',
                     help="1-based index to start replacement from."
                )
            with c2:
                params['num_chars'] = st.number_input(
                    "Num chars",
                    min_value=0, value=st.session_state.get('rt_num_chars', 0), step=1, key='rt_num_chars',
                    help="Number of characters to replace."
                )
            with c3:
                params['replacement_text'] = st.text_input(
                    "Replacement text",
                    value=st.session_state.get('rt_replacement_text', ""), key='rt_replacement_text'
                )

        # --- Calculate and display preview ---
        st.markdown("**Preview of Final Filenames:**")
        st.session_state.final_renamed_data = [] # Recalculate final names
        error_occurred = False
        preview_lines = []

        for i, file_info in enumerate(st.session_state.sorted_file_info):
            initial_name = file_info['initial_rename']
            final_name = initial_name # Default to initial if operation fails or does nothing
            preview_highlighted = initial_name # Default preview
            valid_op = True

            try:
                if rename_operation == "Remove Characters" and params.get('num_chars', 0) > 0:
                    start_0_based = params['start_index'] - 1
                    num_chars_to_remove = params['num_chars']
                    end_0_based = start_0_based + num_chars_to_remove
                    if 0 <= start_0_based < len(initial_name) and end_0_based <= len(initial_name):
                        final_name = initial_name[:start_0_based] + initial_name[end_0_based:]
                        # Highlight the actual characters to be removed
                        preview_highlighted = (
                            f"{initial_name[:start_0_based]}"
                            f"<span style='background-color:rgba(255,0,0,0.4); color:white; padding: 0 2px; border-radius: 3px;'>"
                            f"{initial_name[start_0_based:end_0_based]}"
                            f"</span>"
                            f"{initial_name[end_0_based:]}"
                        )
                    else:
                        st.warning(f"Invalid remove range for: {initial_name}")
                        error_occurred = True
                        valid_op = False

                elif rename_operation == "Add Text" and params.get('text_to_add'):
                    pos_0_based = params['position'] - 1
                    text_to_add = params['text_to_add']
                    if 0 <= pos_0_based <= len(initial_name):
                        final_name = initial_name[:pos_0_based] + text_to_add + initial_name[pos_0_based:]
                        # Highlight the insertion point with added text shown
                        preview_highlighted = (
                             f"{initial_name[:pos_0_based]}"
                             f"<span style='color:blue; font-weight:bold; border-bottom: 2px solid blue;'>|</span>"
                             f"<span style='background-color:rgba(0,255,0,0.3); color:black; padding: 0 2px; border-radius: 3px;'>{text_to_add}</span>"
                             f"{initial_name[pos_0_based:]}"
                        )
                    else:
                        st.warning(f"Invalid add position for: {initial_name}")
                        error_occurred = True
                        valid_op = False

                elif rename_operation == "Replace Text":
                    start_0_based = params['start_index'] - 1
                    num_chars_to_replace = params.get('num_chars', 0)
                    replacement_text = params.get('replacement_text', '')
                    end_0_based = start_0_based + num_chars_to_replace
                    if 0 <= start_0_based < len(initial_name) and end_0_based <= len(initial_name):
                        final_name = initial_name[:start_0_based] + replacement_text + initial_name[end_0_based:]
                        # Highlight the section to be replaced and show replacement
                        preview_highlighted = (
                            f"{initial_name[:start_0_based]}"
                            f"<span style='background-color:rgba(255,0,0,0.4); text-decoration: line-through; color:white; padding: 0 2px; border-radius: 3px;'>"
                            f"{initial_name[start_0_based:end_0_based]}"
                            f"</span>"
                            f"<span style='background-color:rgba(0,255,0,0.3); color:black; padding: 0 2px; border-radius: 3px;'>{replacement_text}</span>"
                            f"{initial_name[end_0_based:]}"
                        )
                    else:
                        st.warning(f"Invalid replace range for: {initial_name}")
                        error_occurred = True
                        valid_op = False

            except Exception as e:
                st.error(f"Error processing {initial_name}: {e}")
                error_occurred = True
                valid_op = False
                final_name = initial_name # Reset on error

            # Store final name and original data for download if operation was valid
            original_data = st.session_state.file_data_map.get(file_info['original_filename'])
            if original_data:
                st.session_state.final_renamed_data.append((final_name, original_data))
            else:
                st.error(f"Internal error: Could not find data for {file_info['original_filename']} during final rename.")
                error_occurred = True # Prevent download if data is missing

            # Add to preview list with smaller font size
            preview_lines.append(f"<div style='font-size: 0.9em; margin-bottom: 10px;'>") # Start div with style
            preview_lines.append(f"**{i+1}. Initial:** `{initial_name}`<br>")
            preview_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;**Preview:** {preview_highlighted}<br>")
            preview_lines.append(f"<span style='color: green;'>&nbsp;&nbsp;&nbsp;&nbsp;**Final:** `{final_name}`</span>")
            preview_lines.append(f"</div>") # End div
            preview_lines.append("--- ") # Separator

        # Display the preview using markdown
        st.markdown("\n".join(preview_lines), unsafe_allow_html=True)

        if error_occurred:
            st.error("One or more filenames encountered an error or invalid parameters during renaming. Please check warnings and adjust inputs. Download will use the names shown in the 'Final' preview.")
        # --- Download Button --- (Uses st.session_state.final_renamed_data)
        if st.session_state.final_renamed_data:
            # Create zip file in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for final_filename, data in st.session_state.final_renamed_data:
                    zip_file.writestr(final_filename, data)
            zip_buffer.seek(0)

            st.download_button(
                label="Download Final Renamed Files as ZIP",
                data=zip_buffer,
                file_name="landr_ordered_renamed_tracks.zip",
                mime="application/zip",
                key="download_button"
            )

    # Handle case where no files were parsed from the upload
    elif not parsed_files and uploaded_files:
        st.warning("No files could be processed. Ensure filenames match the required format `..._keyKey_BPMbpm.wav`.")

else:
    st.info("Upload WAV files to begin.")
    # Clear state when no files are uploaded
    st.session_state.sorted_file_info = []
    st.session_state.file_data_map = {}
    st.session_state.final_renamed_data = [] 
