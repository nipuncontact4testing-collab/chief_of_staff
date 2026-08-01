import os
import sys
import json
from dotenv import load_dotenv

# Ensure the script directory is in python path for importing context_builder
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from context_builder import assemble_context

# 3 Sample threads for draft_machine and approval_gate
SAMPLE_THREADS = [
    {
        "id": "thread_1",
        "title": "Q3 Budget Review",
        "subject": "Q3 Budget Review",
        "messages": [
            {
                "from": "finance@company.com",
                "date": "2026-08-06 10:00:00",
                "body": "Hi Rahul,\n\nWe are finalized on the Q3 budget spreadsheet. Can you review the marketing portion and let us know if any adjustments are needed by Friday end of day?"
            },
            {
                "from": "rahul@company.com",
                "date": "2026-08-06 11:30:00",
                "body": "Hi Finance Team,\n\nI will take a look. Let's make sure we are accounting for the extra dev agency spend.\n\nBest, Rahul"
            },
            {
                "from": "finance@company.com",
                "date": "2026-08-06 12:00:00",
                "body": "Yes, we included the dev agency in line 42. Please confirm if that amount ($15k/month) looks correct."
            }
        ]
    },
    {
        "id": "thread_2",
        "title": "Marketing Campaign Timeline",
        "subject": "Re: Marketing Campaign Launch",
        "messages": [
            {
                "from": "marketing@company.com",
                "date": "2026-08-05 09:15:00",
                "body": "Hi Rahul,\n\nWe are planning to kick off the new feature campaign on September 1st. Will the product onboarding changes be fully deployed and tested by then? We need a firm confirmation before locking in the ad spend."
            }
        ]
    },
    {
        "id": "thread_3",
        "title": "New Feature Request - Analytics",
        "subject": "Feedback: Customer Analytics request",
        "messages": [
            {
                "from": "customer_success@company.com",
                "date": "2026-08-04 14:00:00",
                "body": "Hi Rahul,\n\nSeveral enterprise clients are asking for a CSV export option on the analytics dashboard. Is this something we can add to the near-term roadmap? It would save CS a lot of time doing manual reports."
            }
        ]
    }
]

# Load environment variables
load_dotenv(os.path.join(script_dir, ".env"))

# Configure Gemini
api_key = os.environ.get("GENAI_API_KEY")
if api_key and genai:
    genai.configure(api_key=api_key)

def draft_reply(thread):
    """
    Calls assemble_context() to get the system + user prompts,
    adds the drafting rules, calls Gemini, and returns ONLY the draft text.
    """
    if not api_key:
        raise ValueError("GENAI_API_KEY environment variable is missing.")
    if not genai:
        raise ImportError("google-generativeai package is not installed.")

    # 1. Get the system and user prompts
    # Ensure tone_profile.json and past_replies.json paths are resolved correctly relative to script directory
    tone_path = os.path.join(script_dir, "tone_profile.json")
    replies_path = os.path.join(script_dir, "past_replies.json")
    
    context = assemble_context(thread, tone_path=tone_path, replies_path=replies_path)
    system_prompt = context["system"]
    user_prompt = context["user"]

    # 2. Add drafting rules to system prompt
    drafting_rules = """
CRITICAL DRAFTING RULES:
a. ONE-ASK RULE: every email has exactly ONE clear question or ONE clear response.
b. LENGTH CONTROL: match thread energy, max 5 sentences, use numbered points if needed.
c. NO AI FILLER: never say "I hope this finds you well", "Thank you for reaching out", or other polite AI fluff.
d. STRUCTURE: acknowledge briefly -> give response -> ONE clear next step.
e. NO METADATA OR SUBJECT: Do NOT include any Subject line, explanation, notes, or "Body:" label. Return ONLY the raw body text of the reply.
"""
    system_prompt_with_rules = f"{system_prompt}\n\n{drafting_rules}"

    # 3. Call Gemini
    # Trying gemini-1.5-flash-latest as gemini-1.5-flash returned 404
    model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt_with_rules)
    response = model.generate_content(user_prompt)
    
    draft = response.text.strip()
    
    # Clean up accidental subject line or header if generated
    lines = draft.split("\n")
    cleaned_lines = []
    for line in lines:
        if line.lower().startswith("subject:"):
            continue
        if line.lower().startswith("body:"):
            continue
        cleaned_lines.append(line)
        
    draft = "\n".join(cleaned_lines).strip()
    return draft

def draft_reply_with_metadata(thread):
    """
    Returns a dict with:
    - The draft text
    - Model name
    - Thread subject
    - Who we're replying to
    """
    draft_text = draft_reply(thread)
    
    # Identify who we're replying to (the sender of the last message in the thread)
    reply_to = "Unknown"
    messages = thread.get("messages", [])
    if messages:
        # Find the last message that is NOT from Rahul (the user persona)
        # Or if all are from Rahul, just the last message's sender
        for msg in reversed(messages):
            sender = msg.get("from") or msg.get("sender") or ""
            if "rahul" not in sender.lower():
                reply_to = sender
                break
        if reply_to == "Unknown" and messages:
            reply_to = messages[-1].get("from") or messages[-1].get("sender") or "Unknown"

    return {
        "draft": draft_text,
        "model_name": "gemini-2.5-flash",
        "subject": thread.get("subject", "No Subject"),
        "reply_to": reply_to
    }

if __name__ == "__main__":
    # Use the first thread from SAMPLE_THREADS for testing
    sample_thread = SAMPLE_THREADS[0]
    
    print("--- TESTING DRAFT MACHINE ---")
    if not api_key:
        print("\n[ERROR] GENAI_API_KEY is not set in the .env file.")
        print("Please ensure your .env file in /Users/admin/Downloads/Nipun/Masai/HandsOn/Live_Projects/chief_of_staff/.env contains GENAI_API_KEY=your_key")
        sys.exit(1)
        
    try:
        result = draft_reply_with_metadata(sample_thread)
        print("\n==================== GENERATED REPLY WITH METADATA ====================")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\nAn error occurred during drafting: {e}")
