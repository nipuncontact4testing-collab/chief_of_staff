import os
import sys
import json
from datetime import datetime

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

import streamlit as st

# Configure script directory and system path for relative imports
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

from draft_machine import SAMPLE_THREADS, draft_reply

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Page config
st.set_page_config(
    page_title="AI Ghostwriter - Approval Gate",
    page_icon="🤖",
    layout="wide",
)

# Custom Styling (Dark theme and clean card UI)
st.markdown("""
    <style>
    /* Dark Theme Core */
    .stApp {
        background-color: #1a1a2e;
        color: #ffffff;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #11111e !important;
        border-right: 1px solid #2d2d44;
    }
    
    /* Header & Titles */
    h1, h2, h3, h4, h5, h6, label {
        color: #ffffff !important;
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Thread Message Box */
    .message-box {
        background-color: #16213e;
        border-left: 5px solid #0f3460;
        padding: 15px;
        margin-bottom: 15px;
        border-radius: 5px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .message-header {
        font-weight: bold;
        color: #e94560;
        margin-bottom: 5px;
        font-size: 0.95em;
    }
    .message-date {
        font-size: 0.8em;
        color: #a0a0b8;
        margin-bottom: 10px;
    }
    .message-body {
        white-space: pre-wrap;
        color: #e2e2ec;
        font-size: 0.95em;
        line-height: 1.5;
    }
    
    /* Draft display card */
    .draft-box {
        background-color: #1f1e1b;
        border: 2px solid #e0a96d;
        padding: 20px;
        border-radius: 8px;
        font-family: 'Courier New', Courier, monospace;
        white-space: pre-wrap;
        color: #f5f0e1;
        line-height: 1.6;
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    
    /* Status indicators styling */
    .status-approved {
        padding: 12px;
        background-color: #1b4d3e;
        border: 1px solid #2e7d62;
        border-radius: 5px;
        color: #d1ebd5;
        margin-bottom: 15px;
        font-weight: 500;
    }
    .status-rejected {
        padding: 12px;
        background-color: #5c1d1d;
        border: 1px solid #8f2c2c;
        border-radius: 5px;
        color: #f7d6d6;
        margin-bottom: 15px;
        font-weight: 500;
    }
    </style>
""", unsafe_allow_html=True)

# 1. API KEY RESOLUTION & CONFIGURATION
# Load environment variables
load_dotenv(os.path.join(script_dir, ".env"))

api_key = None
try:
    if "GENAI_API_KEY" in st.secrets:
        api_key = st.secrets["GENAI_API_KEY"]
except Exception:
    pass

if not api_key:
    if os.environ.get("GENAI_API_KEY"):
        api_key = os.environ.get("GENAI_API_KEY")

# Sidebar for API key input if not found in secrets/env
st.sidebar.title("Configuration")
if not api_key:
    api_key_input = st.sidebar.text_input("Enter your Gemini API Key", type="password")
    if api_key_input:
        api_key = api_key_input
        os.environ["GENAI_API_KEY"] = api_key
        # Re-configure Google AI module
        genai.configure(api_key=api_key)
else:
    st.sidebar.success("Gemini API Key loaded successfully.")
    # Ensure it's set in os.environ for draft_machine to read
    os.environ["GENAI_API_KEY"] = api_key
    genai.configure(api_key=api_key)

# 2. STATE MANAGEMENT INITIALIZATION
if "current_draft" not in st.session_state:
    st.session_state.current_draft = None
if "status" not in st.session_state:
    st.session_state.status = "none"  # none, approved, editing, rejected
if "generation_count" not in st.session_state:
    st.session_state.generation_count = 0
if "selected_thread" not in st.session_state:
    st.session_state.selected_thread = SAMPLE_THREADS[0]
if "reset_done" not in st.session_state:
    st.session_state.reset_done = False
if "use_real_gmail" not in st.session_state:
    st.session_state.use_real_gmail = False
if "real_threads" not in st.session_state:
    st.session_state.real_threads = []

# Helper function to save approved draft
def save_approved_draft(thread, draft_text):
    path = os.path.join(script_dir, "approved_drafts.json")
    approved_list = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                approved_list = json.load(f)
        except Exception:
            pass
            
    # Find who we're replying to
    reply_to = "Unknown"
    messages = thread.get("messages", [])
    if messages:
        for msg in reversed(messages):
            sender = msg.get("from") or msg.get("sender") or ""
            if "rahul" not in sender.lower():
                reply_to = sender
                break
        if reply_to == "Unknown" and messages:
            reply_to = messages[-1].get("from") or messages[-1].get("sender") or "Unknown"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "source": st.session_state.get("status", "approved"),
        "thread_id": thread.get("id", "custom_pasted"),
        "subject": thread.get("subject", "No Subject"),
        "reply_to": reply_to,
        "char_count": len(draft_text),
        "draft": draft_text
    }
    approved_list.append(entry)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(approved_list, f, indent=2, ensure_ascii=False)

# App Title & Subtitle
st.title("🤖 AI Email Ghostwriter - Approval Gate")
st.subheader("Your secure guardrail for drafts -- review, edit, or reject before sending")

# Option to fetch real gmail messages or use mock data
st.markdown("---")
col_src1, col_src2 = st.columns([1, 1], gap="medium")
with col_src1:
    mail_source_mode = st.radio(
        "Choose Mail Source Mode:",
        ["Use Dummy / Mock Threads", "Use Real Gmail Inbox"],
        index=1 if st.session_state.use_real_gmail else 0,
        horizontal=True
    )
    st.session_state.use_real_gmail = (mail_source_mode == "Use Real Gmail Inbox")
    
with col_src2:
    if st.session_state.use_real_gmail:
        st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
        if st.button("📥 Fetch and Show Gmail Messages", use_container_width=True):
            with st.spinner("Connecting to Gmail MCP and fetching real messages..."):
                try:
                    from engine import fetch_threads
                    fetched_list = fetch_threads()
                    if fetched_list:
                        formatted_threads = []
                        for idx, t in enumerate(fetched_list):
                            formatted_threads.append({
                                "id": t["thread_id"],
                                "title": f"📧 {t['sender'][:25]} - {t['subject'][:35]}",
                                "subject": t["subject"],
                                "messages": [
                                    {
                                        "from": t["sender"],
                                        "date": t["date"],
                                        "body": t.get("body") or t.get("snippet", "No content")
                                    }
                                ]
                            })
                        st.session_state.real_threads = formatted_threads
                        st.session_state.selected_thread = formatted_threads[0]
                        st.session_state.current_draft = None
                        st.session_state.status = "none"
                        st.success(f"Successfully fetched {len(formatted_threads)} threads from Gmail inbox!")
                    else:
                        st.warning("No threads found in your inbox.")
                except Exception as e:
                    st.error(f"Failed to fetch Gmail threads: {e}")

st.markdown("---")

# Determine active thread list
if st.session_state.use_real_gmail:
    active_threads_list = st.session_state.real_threads
else:
    active_threads_list = SAMPLE_THREADS

# 3. SIDEBAR: THREAD SELECTION
st.sidebar.markdown("---")
st.sidebar.subheader("Select Email Thread")

# Dropdown for threads
if active_threads_list:
    thread_titles = [t["title"] for t in active_threads_list]
    
    # Determine default index
    default_index = 0
    if st.session_state.selected_thread and st.session_state.selected_thread["title"] in thread_titles:
        default_index = thread_titles.index(st.session_state.selected_thread["title"])
        
    selected_title = st.sidebar.selectbox("Choose a thread:", thread_titles, index=default_index)
else:
    selected_title = None
    st.sidebar.info("Please fetch messages first.")

# Option to paste custom JSON
st.sidebar.markdown("### Or Paste Custom Thread JSON")
custom_json_input = st.sidebar.text_area(
    "Custom Thread JSON:",
    placeholder='{\n  "subject": "Topic",\n  "messages": [\n    {"from": "user@example.com", "date": "2026-08-01", "body": "Hello!"}\n  ]\n}',
    height=150
)

# Process selection
active_thread = None
if custom_json_input.strip():
    try:
        active_thread = json.loads(custom_json_input)
        if "subject" not in active_thread or "messages" not in active_thread:
            st.sidebar.error("Custom JSON must include 'subject' and 'messages' list.")
            active_thread = None
    except json.JSONDecodeError as e:
        st.sidebar.error(f"Invalid JSON format: {e}")
        active_thread = None

if active_thread is None and active_threads_list:
    # Fall back to selected dropdown thread
    for t in active_threads_list:
        if t["title"] == selected_title:
            active_thread = t
            break

# Update state if thread changes
if active_thread != st.session_state.selected_thread:
    st.session_state.selected_thread = active_thread
    st.session_state.current_draft = None
    st.session_state.status = "none"
    st.session_state.reset_done = False

# Sidebar: Generate button
if st.sidebar.button("✨ Generate Draft", use_container_width=True):
    if not api_key:
        st.sidebar.error("Please configure your Gemini API Key first.")
    else:
        with st.sidebar.spinner("Drafting reply with Gemini..."):
            try:
                # Trigger draft generation
                st.session_state.reset_done = False
                draft_text = draft_reply(active_thread)
                st.session_state.current_draft = draft_text
                st.session_state.status = "none"
                st.session_state.generation_count += 1
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Generation error: {e}")

# Sidebar: Session Stats & Reset Session
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Session Stats")

col_stat1, col_stat2 = st.sidebar.columns(2)
with col_stat1:
    st.sidebar.metric("Drafts Generated", st.session_state.generation_count)
with col_stat2:
    status_label = st.session_state.status.upper()
    st.sidebar.metric("Current Status", status_label)

if st.sidebar.button("🔄 Reset Session", use_container_width=True):
    st.session_state.current_draft = None
    st.session_state.status = "none"
    st.session_state.generation_count = 0
    st.session_state.reset_done = True
    st.rerun()

if st.session_state.get("reset_done", False):
    st.sidebar.success("✅ Session Reset Done")

# 4. MAIN LAYOUT: TWO COLUMNS
col1, col2 = st.columns([1, 1], gap="large")

# Left Column: Thread History
with col1:
    st.markdown("### 📧 Email Thread History")
    if active_thread:
        st.markdown(f"**Subject:** `{active_thread.get('subject', 'No Subject')}`")
        st.markdown("---")
        for i, msg in enumerate(active_thread.get("messages", [])):
            sender = msg.get("from") or msg.get("sender") or "Unknown"
            date = msg.get("date", "Unknown Date")
            body = msg.get("body", "")
            
            # Message Container
            st.markdown(f"""
                <div class="message-box">
                    <div class="message-header">📩 {sender}</div>
                    <div class="message-date">{date}</div>
                    <div class="message-body">{body}</div>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Select or paste an email thread in the sidebar to view history.")

# Right Column: Draft Workspace & Human Gate
with col2:
    st.markdown("### 📝 Draft Workspace")
    
    if st.session_state.current_draft is None:
        st.info("Click '✨ Generate Draft' in the sidebar to generate a ghostwritten response.")
    else:
        # Status indicators
        if st.session_state.status == "approved":
            st.markdown("""
                <div class="status-approved">
                    ✅ <b>DRAFT APPROVED:</b> This reply has been marked as 'ready to send' and saved to approved_drafts.json.
                </div>
            """, unsafe_allow_html=True)
            
        elif st.session_state.status == "rejected":
            st.markdown("""
                <div class="status-rejected">
                    ❌ <b>DRAFT REJECTED:</b> This draft has been discarded. Click 'Generate Draft' to create a new version.
                </div>
            """, unsafe_allow_html=True)
            
        elif st.session_state.status == "editing":
            st.info("✏️ <b>EDIT MODE:</b> Modify the draft text below and click Approve to finalize.")

        # Draft Display/Edit box
        if st.session_state.status == "editing":
            edited_draft = st.text_area(
                "Modify Draft Text:",
                value=st.session_state.current_draft,
                height=250
            )
            
            col_save, col_cancel = st.columns([1, 1])
            with col_save:
                if st.button("💾 Save & Approve Edited Version", use_container_width=True):
                    st.session_state.current_draft = edited_draft
                    save_approved_draft(active_thread, edited_draft)
                    st.session_state.status = "approved"
                    st.rerun()
            with col_cancel:
                if st.button("Cancel Edit", use_container_width=True):
                    st.session_state.status = "none"
                    st.rerun()
                    
        else:
            # Display draft
            st.markdown(f"""
                <div class="draft-box">{st.session_state.current_draft}</div>
            """, unsafe_allow_html=True)
            
        st.markdown("")
        
        # Display buttons if draft status is 'none' (not approved, edited, or rejected yet)
        if st.session_state.status == "none":
            btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
            
            with btn_col1:
                if st.button("✅ Approve", use_container_width=True):
                    save_approved_draft(active_thread, st.session_state.current_draft)
                    st.session_state.status = "approved"
                    st.rerun()
                    
            with btn_col2:
                if st.button("✏️ Edit", use_container_width=True):
                    st.session_state.status = "editing"
                    st.rerun()
                    
            with btn_col3:
                if st.button("❌ Reject", use_container_width=True):
                    st.session_state.status = "rejected"
                    st.rerun()
                    
        # If draft was approved or rejected, allow resetting/drafting a new one
        elif st.session_state.status in ["approved", "rejected"]:
            if st.button("🔄 Start New Draft Process", use_container_width=True):
                st.session_state.current_draft = None
                st.session_state.status = "none"
                st.rerun()

    # Footer help section inside the Right Column
    st.markdown("---")
    with st.expander("ℹ️ How this gate works", expanded=False):
        st.markdown("""
        ### 🛡️ Human-in-the-Loop (HITL) Guardrail
        This approval gate acts as a secure human layer between the AI Ghostwriter and your actual recipients.
        
        #### **Core Principles & Features:**
        1. **Never Auto-Send:** No AI output is ever transmitted automatically. This prevents hallucinated, incorrect, or off-tone drafts from reaching your clients or teammates.
        2. **Three-Way Gatekeeping:**
           * ✅ **Approve:** Marks the draft as perfect. Saves the finalized text, recipient metadata, and a precise timestamp to `approved_drafts.json` for queuing/sending.
           * ✏️ **Edit:** Renders an inline text-area pre-populated with the draft, allowing you to fine-tune the phrasing, correct specifics, or add custom notes before final approval.
           * ❌ **Reject:** Flags the current draft as unacceptable. Clears state and prompts a clean slate or regeneration.
        3. **Tone Profile Alignment:** Every draft is processed by our context builder, aligning output strictly with the user's specific quirks, rules, and historical replies.
        4. **Flexible Input:** Run drafts against standard mock threads or paste any raw thread history JSON directly into the sidebar to test on-the-fly.
        """)
