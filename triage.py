import os
try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()

if genai is not None:
    try:
        genai.configure(api_key=os.environ.get("GENAI_API_KEY"))
        model = genai.GenerativeModel("gemini-3.0-flash")
    except Exception:
        model = None
else:
    model = None

def triage_thread(sender: str, subject: str, snippet: str) -> dict:
    prompt = f"""
        You are an expert email triage assistant, helping to triage an inbox.
        
        For each thread, classify it into exactly one priority:

        Sender: {sender}
        Subject: {subject}
        Snippet: {snippet}

        Resond in this exact format:
        Priority: <urgent | needs-reply | fyi | ignore>
        Category: <one short tag like: meeting-request, follow-up, newsletter, billing, job-app>
        Reason: <one short sentence explaining your reasoning>
        """
    
    # Try using the LLM if available, otherwise fall back to a simple heuristic
    if model is not None:
        try:
            response = model.generate_content(prompt)
            print(f"LLM response: {response.text}")
            return parse_triage_response(response.text)
        except Exception:
            pass

    # Simple offline heuristic fallback
    return simple_triage(sender, subject, snippet)


def simple_triage(sender: str, subject: str, snippet: str) -> dict:
    s = f"{sender} {subject} {snippet}".lower()
    if 'urgent' in s or 'asap' in s or 'escalat' in s:
        return {'Priority': 'urgent', 'Category': 'escalation', 'Reason': 'explicit urgent language'}
    if 'invoice' in s or 'billing' in s or 'payment' in s:
        return {'Priority': 'needs-reply', 'Category': 'billing', 'Reason': 'billing or invoice related'}
    if 'opportunity' in s or 'recruit' in s or 'interview' in s:
        return {'Priority': 'needs-reply', 'Category': 'job-app', 'Reason': 'recruiter or job opportunity'}
    if 'newsletter' in s or 'articles' in s or 'newsletter@' in s:
        return {'Priority': 'fyi', 'Category': 'newsletter', 'Reason': 'newsletter content'}
    return {'Priority': 'ignore', 'Category': 'other', 'Reason': 'no action required'}

def parse_triage_response(response_text: str) -> dict:
    result = {'Priority': None, 'Category': None, 'Reason': None}
    lines = response_text.strip().split('\n')
    for line in lines:
        if line.startswith('Priority:'):
            result['Priority'] = line.split(':', 1)[1].strip().lower()
        elif line.startswith('Category:'):
            result['Category'] = line.split(':', 1)[1].strip().lower()
        elif line.startswith('Reason:'):
            result['Reason'] = line.split(':', 1)[1].strip().lower()
    return result

def triage_inbox(threads: list) -> list:
    triaged_results = []
    for thread in threads:
        label = triage_thread(sender = thread['sender'], subject = thread['subject'], snippet = thread['snippet'])
        triaged_results.append({**thread, **label})


    priority_order = {'urgent': 0, 'needs-reply': 1, 'fyi': 2, 'ignore': 3, 'unknown': 4}

    triaged_results.sort(key=lambda x: priority_order.get(x['Priority'], 4))

    return triaged_results

sample_threads = [
    {'sender': 'boss@company.com', 'subject': 'URGENT: Client escalation, need response today', 'snippet': 'can you review the proposal and provide feedback by EOD?'},
    {'sender': 'newsletter@medium.com', 'subject': '10 articles you might like this week', 'snippet': 'Here are some articles that might interest you this week.'},
    {'sender': 'recruiter@linkedin.com', 'subject': 'Exciting opportunity at fast growing startup', 'snippet': 'We have an exciting opportunity for a talented professional like you.'}
]

def format_digest(results: list):
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    total_threads = len(results)
    
    print(f"Your Inbox Digest - {today} | Total Threads: {total_threads}")
    print("=" * 60)
    
    prev_priority = None
    for res in results:
        priority = res.get('Priority', 'unknown')
        if prev_priority is not None and priority != prev_priority:
            print("-" * 60)
            
        p_label = str(priority).upper()
        sender = res.get('sender', '')
        subject = res.get('subject', '')
        reason = res.get('Reason', '')
        
        print(f"[{p_label}] {sender} | {subject} - {reason}")
        prev_priority = priority

#results = triage_inbox(sample_threads)

#format_digest(results)
