import json
import os
from datetime import datetime

LOG_FILE = "action_log.json"

def log_action(action_type, thread_subject, detail, action_id):
    """
    Appends a record to action_log.json
    - action_type: "sent" or "booked"
    - detail: recipient email (for "sent") or meeting title (for "booked")
    - action_id: Gmail message_id or Google Calendar event_id
    """
    timestamp = datetime.now().isoformat()
    
    new_record = {
        "timestamp": timestamp,
        "action_type": action_type,
        "thread_subject": thread_subject,
        "detail": detail,
        "id": action_id
    }
    
    log_data = get_action_log()
    log_data.append(new_record)
    
    with open(LOG_FILE, "w") as f:
        json.dump(log_data, f, indent=4)

def get_action_log():
    """
    Reads action_log.json and returns the full list.
    Returns [] if the file does not exist or is empty.
    """
    if not os.path.exists(LOG_FILE):
        return []
    
    try:
        with open(LOG_FILE, "r") as f:
            content = f.read()
            if not content:
                return []
            return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return []

def clear_log():
    """
    Writes an empty list to action_log.json
    """
    with open(LOG_FILE, "w") as f:
        json.dump([], f, indent=4)
