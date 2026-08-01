import streamlit as st
import json
import os
import sys
from datetime import datetime

# Ensure the chief_of_staff directory is in path so we can import the other modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from engine import fetch_threads
from triage import triage_inbox
from draft_machine import draft_reply
from task_logger import get_action_log

# Page config
st.set_page_config(page_title="The Draft Desk", page_icon="✍️", layout="wide")

def _init_session_state():
    """Initializes all required session state variables with defaults."""
    defaults = {
        "source": "Sample threads for demo",
        "threads": [],
        "pipeline_running": False,
        "pipeline_log": [],
        "triaged": {
            "urgent": [],
            "needs-reply": [],
            "fyi": [],
            "ignore": []
        },
        "drafts": {},
        "approved": {},
        "rejected": set(),
        "current_phase": "Inbox & Triage"
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_session_state()

def render_sidebar():
    """Renders the sidebar with navigation and pipeline controls."""
    st.sidebar.title("The Draft Desk")
    st.sidebar.caption("The Chief of Staff AI")
    st.sidebar.divider()

    # Source selection moved to top to ensure state persistence
    options = ["Gmail via engine.py", "Sample threads for demo"]
    current_source = st.session_state.get("source", options[1])
    try:
        source_idx = options.index(current_source)
    except ValueError:
        source_idx = 1

    st.sidebar.radio(
        "Select Source",
        options=options,
        index=source_idx,
        key="source"
    )
    st.sidebar.divider()
    
    if st.sidebar.button("Run Full Pipeline", type="primary", use_container_width=True, key="run_pipeline_btn"):
        st.session_state.pipeline_running = True
        st.rerun()
    st.sidebar.caption("Fetches, triages, and drafts -- stops at Approval Gate.")
    st.sidebar.divider()

    # Navigation buttons
    st.sidebar.markdown("### Workflow Navigation")
    
    phases = ["Inbox & Triage", "Draft Generation", "Approval Gate", "Export Proof"]
    keys = ["nav_inbox_btn", "nav_draft_btn", "nav_approval_btn", "nav_export_btn"]
    
    for phase, key in zip(phases, keys):
        label = f"👉 {phase}" if st.session_state.current_phase == phase else phase
        if st.sidebar.button(label, use_container_width=True, key=key):
            st.session_state.current_phase = phase
            st.rerun()

def convert_engine_threads_to_pipeline_format(engine_threads):
    """
    Converts engine.py output format:
    [{thread_id, sender, subject, snippet, date}]
    into the pipeline format:
    [{id, subject, messages: [{from, date, body}]}]
    """
    pipeline_threads = []
    for thread in engine_threads:
        pipeline_threads.append({
            "id": thread["thread_id"],
            "subject": thread["subject"],
            "messages": [{
                "from": thread["sender"],
                "date": thread.get("date", ""),
                "body": thread["snippet"]  # snippet becomes body for now
            }],
            "Priority": thread.get("Priority"),
            "Category": thread.get("Category"),
            "Reason": thread.get("Reason")
        })
    return pipeline_threads


def load_sample_threads():
    """
    Loads sample threads from sample_threads.json.
    """
    json_path = os.path.join(current_dir, "sample_threads.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError("sample_threads.json not found in project folder!")
    with open(json_path, "r") as f:
        return json.load(f)


def fetch_threads_via_engine():
    """
    Fetches raw threads using fetch_threads() from engine.py.
    """
    return fetch_threads()


def triage_threads(threads):
    """
    Triages fetched threads, converts them to pipeline format,
    and groups them in st.session_state.triaged and st.session_state.threads.
    """
    if not threads:
        return []
    
    # Check if we need to adapt from sample thread format
    if len(threads) > 0 and "messages" in threads[0] and "id" in threads[0]:
        adapted_threads = []
        for thread in threads:
            first_msg = thread["messages"][0] if thread.get("messages") else {"from": "", "date": "", "body": ""}
            adapted_threads.append({
                "sender": first_msg.get("from", ""),
                "subject": thread.get("subject", ""),
                "snippet": first_msg.get("body", ""),
                "thread_id": thread.get("id", ""),
                "date": first_msg.get("date", "")
            })
        triaged_raw = triage_inbox(adapted_threads)
    else:
        triaged_raw = triage_inbox(threads)
        
    pipeline_threads = convert_engine_threads_to_pipeline_format(triaged_raw)
    
    # Store sorted/triaged threads in session state
    st.session_state.threads = pipeline_threads
    
    # Group them by priority
    grouped = {
        "urgent": [],
        "needs-reply": [],
        "fyi": [],
        "ignore": []
    }
    
    for thread in pipeline_threads:
        priority = thread.get("Priority", "ignore")
        if priority in grouped:
            grouped[priority].append(thread)
        else:
            grouped["ignore"].append(thread)
            
    st.session_state.triaged = grouped
    return pipeline_threads


def _get_draft_reply(thread):
    """
    Calls draft_reply(thread) from draft_machine.py.
    """
    return draft_reply(thread)


def run_full_pipeline():
    """
    Runs the full pipeline. Handles errors at each step and returns log strings.
    """
    logs = []
    
    # (1) determine thread source
    try:
        source = st.session_state.source
        logs.append(f"Determined source: {source}")
    except Exception as e:
        logs.append(f"Error reading thread source: {e}")
        source = "Sample threads for demo"
        
    # (2) fetch threads
    fetched_threads = []
    try:
        if source == "Gmail via engine.py":
            fetched_threads = fetch_threads_via_engine()
        else:
            fetched_threads = load_sample_threads()
        logs.append(f"Fetched {len(fetched_threads)} threads...")
    except Exception as e:
        logs.append(f"Error fetching threads: {e}")
        fetched_threads = []
        
    # (3) call triage_threads
    pipeline_threads = []
    try:
        pipeline_threads = triage_threads(fetched_threads)
        triaged = st.session_state.get("triaged", {})
        u_count = len(triaged.get("urgent", []))
        nr_count = len(triaged.get("needs-reply", []))
        logs.append(f"Triaged: {u_count} urgent, {nr_count} needs-reply, {len(triaged.get('fyi', []))} fyi, {len(triaged.get('ignore', []))} ignore")
    except Exception as e:
        logs.append(f"Error triaging threads: {e}")
        
    # (4) reset all downstream session state
    try:
        st.session_state.drafts = {}
        st.session_state.approved = {}
        st.session_state.rejected = set()
        st.session_state.sent = []
        st.session_state.booked = []
        logs.append("Reset downstream session state.")
    except Exception as e:
        logs.append(f"Error resetting session state: {e}")
        
    # (5) loop over urgent + needs-reply and call draft_reply via _get_draft_reply()
    try:
        triaged = st.session_state.get("triaged", {})
        actionable_threads = triaged.get("urgent", []) + triaged.get("needs-reply", [])
        total_actionable = len(actionable_threads)
        
        for idx, thread in enumerate(actionable_threads, 1):
            thread_id = thread.get("id")
            subject = thread.get("subject", "No Subject")
            try:
                draft_text = _get_draft_reply(thread)
                st.session_state.drafts[thread_id] = draft_text
                logs.append(f"Draft {idx}/{total_actionable}: '{subject}'...done")
            except Exception as e:
                logs.append(f"Draft {idx}/{total_actionable}: '{subject}'...failed: {e}")
    except Exception as e:
        logs.append(f"Error generating drafts: {e}")
        
    # (6) set current_phase to Approval Gate
    try:
        st.session_state.current_phase = "Approval Gate"
        logs.append("Set current phase to 'Approval Gate'.")
    except Exception as e:
        logs.append(f"Error setting phase: {e}")
        
    # (7) return log
    drafts_count = len(st.session_state.get("drafts", {}))
    logs.append(f"Pipeline complete! {drafts_count} drafts ready for review.")
    return logs


def _render_pipeline_execution():
    """
    Executes the full pipeline with live progress UI.
    Does NOT call run_full_pipeline() directly, but runs the logic inline to support progress UI.
    """
    pipeline_log = []
    
    with st.status("Running full pipeline...", expanded=True) as status:
        # --- Step 1: Thread Source & Fetching ---
        status.update(label="Step 1/3: Fetching threads...")
        try:
            source = st.session_state.source
            pipeline_log.append(f"Determined source: {source}")
        except Exception as e:
            pipeline_log.append(f"Error reading thread source: {e}")
            source = "Sample threads for demo"
            
        fetched_threads = []
        try:
            if source == "Gmail via engine.py":
                fetched_threads = fetch_threads_via_engine()
            else:
                fetched_threads = load_sample_threads()
            
            pipeline_log.append(f"Fetched {len(fetched_threads)} threads...")
            st.write(f"✅ Fetched {len(fetched_threads)} threads from source: *{source}*")
        except Exception as e:
            msg = f"❌ Error fetching threads: {e}"
            pipeline_log.append(msg)
            st.write(msg)
            status.update(label="Pipeline failed during fetching.", state="error")
            st.session_state.pipeline_log = pipeline_log
            st.session_state.pipeline_running = False
            return
            
        # --- Step 2: Inbox & Triage ---
        status.update(label="Step 2/3: Triaging threads...")
        try:
            pipeline_threads = triage_threads(fetched_threads)
            triaged = st.session_state.get("triaged", {})
            u_count = len(triaged.get("urgent", []))
            nr_count = len(triaged.get("needs-reply", []))
            f_count = len(triaged.get("fyi", []))
            i_count = len(triaged.get("ignore", []))
            
            pipeline_log.append(f"Triaged: {u_count} urgent, {nr_count} needs-reply, {f_count} fyi, {i_count} ignore")
            st.write(f"✅ Triaged successfully! Actionable: {u_count + nr_count} (Urgent: {u_count}, Needs-Reply: {nr_count})")
        except Exception as e:
            msg = f"❌ Error during triage: {e}"
            pipeline_log.append(msg)
            st.write(msg)
            status.update(label="Pipeline failed during triage.", state="error")
            st.session_state.pipeline_log = pipeline_log
            st.session_state.pipeline_running = False
            return
            
        # --- Reset Downstream State ---
        try:
            st.session_state.drafts = {}
            st.session_state.approved = {}
            st.session_state.rejected = set()
            st.session_state.sent = []
            st.session_state.booked = []
            pipeline_log.append("Reset downstream session state.")
        except Exception as e:
            pipeline_log.append(f"Error resetting session state: {e}")
            
        # --- Step 3: Draft Generation Loop ---
        status.update(label="Step 3/3: Generating drafts...")
        try:
            triaged = st.session_state.get("triaged", {})
            actionable_threads = triaged.get("urgent", []) + triaged.get("needs-reply", [])
            total_actionable = len(actionable_threads)
            
            for idx, thread in enumerate(actionable_threads, 1):
                thread_id = thread.get("id")
                subject = thread.get("subject", "No Subject")
                
                status.update(label=f"Step 3/3: Generating draft {idx}/{total_actionable} ('{subject}')...")
                try:
                    draft_text = _get_draft_reply(thread)
                    st.session_state.drafts[thread_id] = draft_text
                    
                    pipeline_log.append(f"Draft {idx}/{total_actionable}: '{subject}'...done")
                    st.write(f"✅ Draft {idx}/{total_actionable}: *{subject}* generated successfully.")
                except Exception as e:
                    pipeline_log.append(f"Draft {idx}/{total_actionable}: '{subject}'...failed: {e}")
                    st.write(f"❌ Draft {idx}/{total_actionable}: *{subject}* failed to generate: {e}")
        except Exception as e:
            msg = f"❌ Error during draft generation loop: {e}"
            pipeline_log.append(msg)
            st.write(msg)
            status.update(label="Pipeline failed during draft generation.", state="error")
            st.session_state.pipeline_log = pipeline_log
            st.session_state.pipeline_running = False
            return
            
        # Complete
        drafts_count = len(st.session_state.get("drafts", {}))
        pipeline_log.append(f"Pipeline complete! {drafts_count} drafts ready for review.")
        status.update(label="Pipeline execution complete!", state="complete")
        
    # Outside the status block: store log, set phase, set running flag, rerun
    st.session_state.pipeline_log = pipeline_log
    st.session_state.current_phase = "Approval Gate"
    st.session_state.pipeline_running = False
    st.rerun()

def render_phase():
    """Renders the content for the currently selected phase."""
    st.title(f"✍️ {st.session_state.current_phase}")

    if st.session_state.current_phase == "Inbox & Triage":
        st.subheader("Pull, Triage, and Classify Emails")
        
        if st.button("Pull & Triage Threads", type="primary"):
            with st.spinner("Fetching and triaging threads..."):
                raw_threads = []
                if st.session_state.source == "Gmail via engine.py":
                    try:
                        # fetch threads from engine.py
                        raw_fetched = fetch_threads()
                        # triage_inbox expects list of dicts with: sender, subject, snippet
                        triaged_raw = triage_inbox(raw_fetched)
                        raw_threads = convert_engine_threads_to_pipeline_format(triaged_raw)
                    except Exception as e:
                        st.error(f"Error fetching/triaging Gmail threads: {e}")
                        raw_threads = []
                else:
                    # Load from sample_threads.json
                    json_path = os.path.join(current_dir, "sample_threads.json")
                    if os.path.exists(json_path):
                        try:
                            with open(json_path, "r") as f:
                                sample_data = json.load(f)
                            
                            # Adapt sample threads for triage_inbox (requires sender, subject, snippet)
                            adapted_threads = []
                            for thread in sample_data:
                                first_msg = thread["messages"][0] if thread.get("messages") else {"from": "", "date": "", "body": ""}
                                adapted_threads.append({
                                    "sender": first_msg.get("from", ""),
                                    "subject": thread["subject"],
                                    "snippet": first_msg.get("body", ""),
                                    "thread_id": thread["id"],
                                    "date": first_msg.get("date", "")
                                })
                            
                            triaged_raw = triage_inbox(adapted_threads)
                            raw_threads = convert_engine_threads_to_pipeline_format(triaged_raw)
                        except Exception as e:
                            st.error(f"Error loading/triaging sample threads: {e}")
                            raw_threads = []
                    else:
                        st.error("sample_threads.json not found in project folder!")
                        raw_threads = []
                
                # Store sorted/triaged threads in session state
                st.session_state.threads = raw_threads
                
                # Group them by priority for display
                grouped = {
                    "urgent": [],
                    "needs-reply": [],
                    "fyi": [],
                    "ignore": []
                }
                
                for thread in raw_threads:
                    priority = thread.get("Priority", "ignore")
                    if priority in grouped:
                        grouped[priority].append(thread)
                    else:
                        grouped["ignore"].append(thread)
                
                st.session_state.triaged = grouped
                st.success("Triage completed successfully!")

        # Display threads grouped by priority
        if st.session_state.threads:
            urgent_count = len(st.session_state.triaged.get("urgent", []))
            needs_reply_count = len(st.session_state.triaged.get("needs-reply", []))
            actionable_count = urgent_count + needs_reply_count
            
            st.markdown(f"### Actionable Threads: **{actionable_count}** (Urgent: {urgent_count}, Needs-Reply: {needs_reply_count})")
            
            priorities = ["urgent", "needs-reply", "fyi", "ignore"]
            for p in priorities:
                threads_in_p = st.session_state.triaged.get(p, [])
                display_title = f"{p.replace('-', ' ').title()} ({len(threads_in_p)})"
                
                with st.expander(display_title, expanded=(p in ["urgent", "needs-reply"])):
                    if not threads_in_p:
                        st.write("No threads in this category.")
                    for thread in threads_in_p:
                        st.markdown(f"#### {thread['subject']}")
                        st.markdown(f"**Category:** `{thread.get('Category', 'N/A')}` | **Reason:** *{thread.get('Reason', 'N/A')}*")
                        
                        # Display messages
                        for msg in thread.get("messages", []):
                            st.markdown(f"- **From:** {msg.get('from')} | **Date:** {msg.get('date')}")
                            st.info(msg.get("body"))
                        st.markdown("---")
        else:
            st.info("No threads loaded. Click 'Pull & Triage Threads' to start.")

    elif st.session_state.current_phase == "Draft Generation":
        st.subheader("Generate Draft Replies for Actionable Emails")
        
        actionable_threads = st.session_state.triaged.get("urgent", []) + st.session_state.triaged.get("needs-reply", [])
        
        if not actionable_threads:
            st.info("No actionable threads available. Please pull and triage threads in the 'Inbox & Triage' phase first.")
        else:
            st.write(f"Found **{len(actionable_threads)}** actionable thread(s) requiring a reply.")
            
            if st.button("Generate All Drafts", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for index, thread in enumerate(actionable_threads):
                    thread_id = thread["id"]
                    subject = thread["subject"]
                    status_text.write(f"Generating draft for thread: *{subject}* ({index + 1}/{len(actionable_threads)})")
                    
                    try:
                        draft_text = draft_reply(thread)
                    except Exception as e:
                        st.warning(f"Failed to generate draft for thread {thread_id} ({e}). Using placeholder.")
                        last_msg = thread["messages"][-1]["body"] if thread["messages"] else ""
                        draft_text = f"Hi,\n\nThank you for the update on '{subject}'. We have received your message and are looking into it.\n\nBest regards,\nRahul"
                    
                    st.session_state.drafts[thread_id] = draft_text
                    progress_bar.progress((index + 1) / len(actionable_threads))
                
                status_text.empty()
                progress_bar.empty()
                st.success("Draft generation complete!")
                st.info("💡 All drafts generated! Head over to the **Approval Gate** phase to review them.")

            st.write("### Review Drafts")
            for thread in actionable_threads:
                thread_id = thread["id"]
                subject = thread["subject"]
                has_draft = thread_id in st.session_state.drafts
                
                expander_title = f"{subject} {'✅ (Draft Ready)' if has_draft else '⏳ (No Draft yet)'}"
                
                with st.expander(expander_title, expanded=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Original Thread:**")
                        if thread.get("messages"):
                            latest_msg = thread["messages"][-1]
                            st.caption(f"From: {latest_msg.get('from')} | Date: {latest_msg.get('date')}")
                            st.info(latest_msg.get("body"))
                    with col2:
                        st.markdown("**AI Draft:**")
                        if has_draft:
                            st.text_area("Draft content", value=st.session_state.drafts[thread_id], key=f"draft_view_{thread_id}", height=150)
                        else:
                            st.write("Draft not generated yet.")

    elif st.session_state.current_phase == "Approval Gate":
        st.subheader("Review, Edit, and Approve Drafts")

        if st.session_state.get("pipeline_log"):
            with st.expander("Pipeline Execution Log", expanded=False):
                for entry in st.session_state.pipeline_log:
                    if "ERROR" in entry.upper() or "FAILED" in entry.upper():
                        st.write(f"❌ {entry}")
                    else:
                        st.write(f"✅ {entry}")
                if st.button("Clear log"):
                    st.session_state.pipeline_log = []
                    st.rerun()
            st.divider()
        
        actionable_threads = st.session_state.triaged.get("urgent", []) + st.session_state.triaged.get("needs-reply", [])
        
        if not actionable_threads:
            st.info("No actionable threads available.")
        else:
            threads_with_drafts = [t for t in actionable_threads if t["id"] in st.session_state.drafts]
            
            if not threads_with_drafts:
                st.info("No drafts have been generated yet.")
            else:
                approved_count = len([t for t in threads_with_drafts if t["id"] in st.session_state.approved])
                rejected_count = len([t for t in threads_with_drafts if t["id"] in st.session_state.rejected])
                pending_threads = [t for t in threads_with_drafts if t["id"] not in st.session_state.approved and t["id"] not in st.session_state.rejected]
                pending_count = len(pending_threads)
                
                st.markdown("### Running Count")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Approved ✅", approved_count)
                col_b.metric("Rejected ❌", rejected_count)
                col_c.metric("Pending Review ⏳", pending_count)
                
                if pending_count == 0 and (approved_count > 0 or rejected_count > 0):
                    st.balloons()
                    st.success("🎉 All drafts reviewed! Proceed to Export Proof.")
                elif pending_count == 0:
                    st.info("All generated drafts are reviewed.")
                else:
                    st.markdown("---")
                    for thread in pending_threads:
                        thread_id = thread["id"]
                        subject = thread["subject"]
                        priority = thread.get("Priority", "needs-reply")
                        emoji = "🔴" if priority == "urgent" else "🟡"
                        
                        st.markdown(f"### {emoji} {subject}")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**History:**")
                            for msg in thread.get("messages", []):
                                st.markdown(f"- **From:** {msg.get('from')} | **Date:** {msg.get('date')}")
                                st.info(msg.get("body"))
                        with col2:
                            st.markdown("**Edit Draft:**")
                            edited_draft = st.text_area("Draft Reply", value=st.session_state.drafts[thread_id], key=f"edit_draft_{thread_id}", height=200)
                            
                        btn_col1, btn_col2, btn_col3, _ = st.columns([1, 1, 1, 3])
                        with btn_col1:
                            if st.button("Approve ✅", key=f"approve_btn_{thread_id}"):
                                st.session_state.approved[thread_id] = edited_draft
                                st.toast(f"Approved: {subject}")
                                st.rerun()
                        with btn_col2:
                            if st.button("Regenerate 🔄", key=f"regen_btn_{thread_id}"):
                                with st.spinner("Regenerating..."):
                                    new_draft = draft_reply(thread)
                                    st.session_state.drafts[thread_id] = new_draft
                                    # Clear the text area's session state to force it to pick up the new value
                                    edit_key = f"edit_draft_{thread_id}"
                                    if edit_key in st.session_state:
                                        del st.session_state[edit_key]
                                    st.rerun()
                        with btn_col3:
                            if st.button("Reject ❌", key=f"reject_btn_{thread_id}"):
                                st.session_state.rejected.add(thread_id)
                                st.rerun()
                        st.markdown("---")

    elif st.session_state.current_phase == "Export Proof":
        st.subheader("Preview and Export Approved Replies")
        if not st.session_state.approved:
            st.info("No approved replies to export yet.")
        else:
            st.write(f"You have **{len(st.session_state.approved)}** approved draft(s) ready.")
            for thread_id, approved_text in st.session_state.approved.items():
                actionable_threads = st.session_state.triaged.get("urgent", []) + st.session_state.triaged.get("needs-reply", [])
                thread = next((t for t in actionable_threads if t["id"] == thread_id), None)
                subject = thread["subject"] if thread else "Unknown Subject"
                with st.expander(f"Approved Reply: {subject}", expanded=True):
                    st.success(approved_text)

            def generate_proof_markdown():
                proof_md = f"# Proof of Work\n\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                for t_id, text in st.session_state.approved.items():
                    proof_md += f"## {t_id}\n\n{text}\n\n"
                return proof_md

            def generate_proof_html():
                html = f"<html><body><h1>Proof of Work</h1><p>{datetime.now()}</p>"
                for t_id, text in st.session_state.approved.items():
                    html += f"<h2>{t_id}</h2><pre>{text}</pre>"
                html += "</body></html>"
                return html

            col_md, col_html = st.columns(2)
            with col_md:
                st.download_button("Download Markdown", data=generate_proof_markdown(), file_name="proof.md")
            with col_html:
                st.download_button("Download HTML", data=generate_proof_html(), file_name="proof.html")

            st.divider()
            st.subheader("Action Log")
            action_log = get_action_log()
            if not action_log:
                st.info("No actions logged yet.")
            else:
                for entry in action_log:
                    col1, col2, col3, col4 = st.columns(4)
                    
                    action_type = entry.get("action_type", "")
                    icon = "📧" if action_type == "sent" else "📅" if action_type == "booked" else ""
                    col1.write(f"{icon} {action_type.upper()}")
                    
                    col2.markdown(f"**{entry.get('thread_subject', '')}**")
                    
                    col3.code(entry.get("detail", ""))
                    
                    ts_str = entry.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        formatted_ts = ts.strftime("%b %d %I:%M %p")
                    except Exception:
                        formatted_ts = ts_str
                    col4.caption(formatted_ts)

def main():
    """Main application entry point."""
    render_sidebar()
    if st.session_state.pipeline_running:
        _render_pipeline_execution()
    else:
        render_phase()

if __name__ == "__main__":
    main()
