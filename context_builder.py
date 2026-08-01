import os
import json

def load_tone_profile(path="tone_profile.json"):
    """Reads and returns the tone profile dict."""
    # Robust path resolution: if path is relative and doesn't exist, check script's directory
    if not os.path.isabs(path) and not os.path.exists(path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        resolved_path = os.path.join(script_dir, path)
        if os.path.exists(resolved_path):
            path = resolved_path
            
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_past_replies(path="past_replies.json"):
    """Reads and returns list of past reply examples."""
    if not os.path.isabs(path) and not os.path.exists(path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        resolved_path = os.path.join(script_dir, path)
        if os.path.exists(resolved_path):
            path = resolved_path
            
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def format_thread_history(thread):
    """
    Takes a thread dict with "subject" and "messages" (list of {from, date, body}) 
    and formats it as a readable string showing who said what in order.
    """
    subject = thread.get("subject", "No Subject")
    messages = thread.get("messages", [])
    
    formatted_lines = []
    formatted_lines.append(f"Subject: {subject}")
    formatted_lines.append("-" * 40)
    
    for i, msg in enumerate(messages, 1):
        # Support both 'from' and 'sender' keys
        sender = msg.get("from") or msg.get("sender") or "Unknown"
        date = msg.get("date", "Unknown Date")
        body = msg.get("body", "").strip()
        
        formatted_lines.append(f"Message #{i}")
        formatted_lines.append(f"From: {sender}")
        formatted_lines.append(f"Date: {date}")
        formatted_lines.append("Content:")
        formatted_lines.append(body)
        formatted_lines.append("-" * 40)
        
    return "\n".join(formatted_lines)

def build_system_prompt(tone_profile, past_replies):
    """
    Builds the system prompt that includes:
    - The persona (name, role, tone, formality)
    - Writing rules from the quirks list
    - 2-3 past reply examples formatted as "Here's how {name} writes:"
    """
    name = tone_profile.get("name", "Rahul")
    role = tone_profile.get("role", "Senior Product Manager")
    tone = tone_profile.get("tone", "professional but warm")
    formality = tone_profile.get("formality", "semi-formal")
    quirks = tone_profile.get("quirks", [])
    
    prompt_parts = []
    
    prompt_parts.append("You are an expert AI email drafting assistant.")
    prompt_parts.append(f"Your persona is:")
    prompt_parts.append(f"- Name: {name}")
    prompt_parts.append(f"- Role: {role}")
    prompt_parts.append(f"- Tone: {tone}")
    prompt_parts.append(f"- Formality: {formality}")
    prompt_parts.append("")
    
    if quirks:
        prompt_parts.append("Please adhere to the following writing rules and quirks:")
        for quirk in quirks:
            prompt_parts.append(f"- {quirk}")
        prompt_parts.append("")
        
    prompt_parts.append(f"Here's how {name} writes:")
    prompt_parts.append("")
    
    for i, reply in enumerate(past_replies):
        subject = reply.get("subject", "Re: email")
        body = reply.get("body", "").strip()
        
        prompt_parts.append(f"Example past reply {i+1}:")
        prompt_parts.append(f"Subject: {subject}")
        prompt_parts.append(f"Body:")
        prompt_parts.append(body)
        prompt_parts.append("-" * 40)
        prompt_parts.append("")
        
    return "\n".join(prompt_parts).strip()

def build_user_prompt(thread_formatted):
    """Builds the user message asking for a reply draft."""
    return f"""Please draft a response to the following email thread, matching the established persona, tone, quirks, and writing style rules.

Email Thread History:
{thread_formatted}
"""

def assemble_context(thread, tone_path="tone_profile.json", replies_path="past_replies.json"):
    """The main function that loads everything and returns a dict: {"system": system_prompt, "user": user_prompt}"""
    tone_profile = load_tone_profile(tone_path)
    past_replies = load_past_replies(replies_path)
    
    system_prompt = build_system_prompt(tone_profile, past_replies)
    thread_formatted = format_thread_history(thread)
    user_prompt = build_user_prompt(thread_formatted)
    
    return {
        "system": system_prompt,
        "user": user_prompt
    }

if __name__ == "__main__":
    # Sample thread for testing and visualization
    sample_thread = {
        "subject": "Question about mobile app checkout flow",
        "messages": [
            {
                "from": "alice@customer.com",
                "date": "2026-08-06 14:30:00",
                "body": "Hi Rahul,\n\nI was trying to use the mobile app today and noticed that the checkout button is hard to tap on smaller screens. Are we planning to optimize this soon?"
            },
            {
                "from": "rahul@company.com",
                "date": "2026-08-06 15:00:00",
                "body": "Hi Alice,\n\nThanks for pointing that out. Yes -- we are currently looking at a design refresh to address accessibility on smaller screens.\n\nBest, Rahul"
            },
            {
                "from": "alice@customer.com",
                "date": "2026-08-06 15:15:00",
                "body": "Great, thanks! Do you have a rough ETA for that release? Our team has a marketing campaign starting next month and we want to align."
            }
        ]
    }
    
    print("--- ASSEMBLING CONTEXT ---")
    context = assemble_context(sample_thread)
    
    print("\n==================== SYSTEM PROMPT ====================")
    print(context["system"])
    
    print("\n==================== USER PROMPT ====================")
    print(context["user"])
