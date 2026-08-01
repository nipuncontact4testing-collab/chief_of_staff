import os
import re
import json
import subprocess
import html
from triage import triage_inbox, format_digest

class MCPClient:
    def __init__(self, mcp_config):
        self.mcp_config = mcp_config
        self.proc = None
        self.msg_id = 1
        
    def connect(self):
        cmd = [self.mcp_config["command"]] + self.mcp_config.get("args", [])
        env = os.environ.copy()
        if "env" in self.mcp_config:
            env.update(self.mcp_config["env"])
            
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        # Handshake: Initialize
        self.msg_id += 1
        init_req = {
            "jsonrpc": "2.0",
            "id": self.msg_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "python-client", "version": "1.0"}
            }
        }
        self.proc.stdin.write(json.dumps(init_req) + "\n")
        self.proc.stdin.flush()
        # Ensure to read the initialization response, it should not be empty
        init_response_line = self.proc.stdout.readline()
        if init_response_line.strip():
            print(f"MCPClient: Init response: {init_response_line.strip()}")
        else:
            print("MCPClient: No init response. This might be an issue.")

        # Handshake: Initialized
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self.proc.stdin.write(json.dumps(init_notif) + "\n")
        self.proc.stdin.flush()
        # Add a short delay after sending the notification and before attempting to read to allow the server to process
        import time
        time.sleep(0.1)  # 100ms delay
        # It\\\"s less critical to read a response for a notification, but we can consume it if present
        # Use select.select with a very short timeout to avoid blocking if no response is expected
        import select
        rlist, _, _ = select.select([self.proc.stdout], [], [], 0.5) # 500ms timeout
        notif_response_line = ""
        if rlist:
            notif_response_line = self.proc.stdout.readline()

        if notif_response_line.strip():
            print(f"MCPClient: Initialized notification response: {notif_response_line.strip()}")
        else:
            print("MCPClient: No response or timed out for initialized notification (expected for notification).")
        
    def call_tool(self, name, arguments):
        self.msg_id += 1
        call_req = {
            "jsonrpc": "2.0",
            "id": self.msg_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        }
        self.proc.stdin.write(json.dumps(call_req) + "\n")
        self.proc.stdin.flush()
        
        # No need for select.select here, readline will block until a newline is received or EOF
        response_line = self.proc.stdout.readline()

        if not response_line.strip():
            # If readline returns empty string, it means EOF, process has exited
            # Read stderr to get any error messages from the MCP server
            stderr_output = self.proc.stderr.read()
            if stderr_output:
                print(f"MCP Server unexpectedly exited. Stderr: {stderr_output}")
            else:
                print("MCPClient: No response received and server did not provide stderr output.")
            return {"error": "No response from MCP server or server exited unexpectedly."}

        if response_line.strip():
            return json.loads(response_line)
        else:
            print(f"MCPClient: No response received for tool call {name}")
            return {"error": "No response from MCP server"}
        
    def close(self):
        if self.proc:
            self.proc.stdin.close()
            self.proc.stdout.close()
            self.proc.stderr.close()
            self.proc.terminate()
            self.proc.wait(timeout=5) # Wait for subprocess to terminate, with a timeout
            self.proc = None

def find_mcp_settings():
    # Try the exact standard path first
    paths = [
        os.path.expanduser("~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"),
        os.path.expanduser("~/Library/Application Support/Cursor/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"),
    ]
    
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    config = json.load(f)
                    if "mcpServers" in config and "gmail" in config["mcpServers"]:
                        return config["mcpServers"]["gmail"]
            except Exception:
                pass
                
    # Fallback to the known location if cline settings cannot be dynamically loaded
    return {
        "command": "node",
        "args": ["/Users/admin/Downloads/Nipun/Masai/HandsOn/Live_Projects/chief_of_staff/gmail-mcp-server/dist/index.js"]
    }

def clean_html(html_content):
    # Strip style/script tags and their contents
    html_content = re.sub(r'<(style|script)[^>]*>([\s\S]*?)</\1>', ' ', html_content, flags=re.IGNORECASE)
    # Replace other HTML tags with space
    text = re.sub(r'<[^>]+>', ' ', html_content)
    # Replace common HTML entities
    text = html.unescape(text)
    # Replace multiple spaces/newlines/returns with a single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_snippet(body, length=150):
    clean_text = clean_html(body)
    if len(clean_text) > length:
        return clean_text[:length].strip() + "..."
    return clean_text

def parse_read_email(text):
    lines = text.split('\n')
    thread_id = None
    subject = None
    sender = None
    date = None
    body_lines = []
    
    header_done = False
    for line in lines:
        if not header_done:
            if line.startswith("Thread ID:"):
                thread_id = line[len("Thread ID:"):].strip()
            elif line.startswith("Subject:"):
                subject = line[len("Subject:"):].strip()
            elif line.startswith("From:"):
                sender = line[len("From:"):].strip()
            elif line.startswith("Date:"):
                date = line[len("Date:"):].strip()
            elif line.strip() == "" and thread_id is not None:
                header_done = True
        else:
            body_lines.append(line)
            
    body = "\n".join(body_lines).strip()
    if body.startswith("[Note: This email is HTML-formatted. Plain text version not available.]"):
        body = body[len("[Note: This email is HTML-formatted. Plain text version not available.]"):].strip()
        
    return {
        "thread_id": thread_id,
        "sender": sender,
        "subject": subject,
        "body": body,
        "date": date
    }

def fetch_threads() -> list:
    mcp_config = find_mcp_settings()
    client = MCPClient(mcp_config)
    client.connect()
    
    try:
        # Search for messages in the inbox (using maxResults=50 to find enough unique threads)
        search_res = client.call_tool("search_emails", {"query": "in:inbox", "maxResults": 50})

        if "error" in search_res or "result" not in search_res:
            print(f"Error searching emails: {search_res.get("error", "Unknown error")}")
            return []

        content_list = search_res["result"].get("content", [])
        if not content_list:
            print("No content found in search results.")
            return []

        text = content_list[0].get("text", "")
        print(f"Raw search result text: {text[:200]}...")
        message_ids = re.findall(r"ID:\s*([a-f0-9]+)", text)
        print(f"Found message IDs: {message_ids}")

        if not message_ids:
            print("No message IDs found in search results. Check Gmail API permissions or if there are actual emails in the inbox.")
            return []
        
        seen_threads = set()
        threads = []
        
        for msg_id in message_ids:
            if len(threads) >= 20:
                break
                
            read_res = client.call_tool("read_email", {"messageId": msg_id})
            if "result" in read_res and "content" in read_res["result"]:
                read_text = read_res["result"]["content"][0].get("text", "")
                parsed = parse_read_email(read_text)
                
                t_id = parsed["thread_id"]
                if t_id and t_id not in seen_threads:
                    seen_threads.add(t_id)
                    snippet_val = get_snippet(parsed["body"])
                    
                    threads.append({
                        "thread_id": t_id,
                        "sender": parsed["sender"],
                        "subject": parsed["subject"],
                        "snippet": snippet_val,
                        "body": parsed["body"],
                        "date": parsed["date"]
                    })
                    
        return threads
    finally:
        client.close()

def send_reply(to, subject, body, thread_id=None, message_id=None, gmail_user_id="me") -> dict:
    """
    Sends a reply to an email thread.
    - Adds "Re: " to the subject if not present.
    - Sets threading parameters (In-Reply-To, References) via message_id.
    - Packages as a MIME text email message and base64url encodes it under-the-hood via the Gmail MCP tool.
    - Returns a dict with message_id, thread_id and status "sent".
    """
    # Ensure "Re: " prefix is added to subject before sending
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
        
    mcp_config = find_mcp_settings()
    client = MCPClient(mcp_config)
    client.connect()
    
    try:
        # Build the arguments for the send_email tool
        args = {
            "to": to if isinstance(to, list) else [to],
            "subject": subject,
            "body": body
        }
        if thread_id:
            args["threadId"] = thread_id
        if message_id:
            args["inReplyTo"] = message_id
            
        # Call the MCP server's send_email tool
        response = client.call_tool("send_email", args)
        
        if "error" in response:
            raise Exception(f"MCP Tool Error: {response['error']}")
            
        # Parse the result to extract message ID
        # Example output text: "Email sent successfully with ID: <id>"
        msg_id = "unknown"
        result_content = response.get("result", {}).get("content", [])
        if result_content:
            text = result_content[0].get("text", "")
            match = re.search(r"ID:\s*([a-f0-9]+)", text)
            if match:
                msg_id = match.group(1)
                
        return {
            "message_id": msg_id,
            "thread_id": thread_id,
            "status": "sent"
        }
    finally:
        client.close()

if __name__ == "__main__":
    print("Fetching last 20 inbox threads...")
    threads = fetch_threads()
    results = triage_inbox(threads)
    print(f"Successfully retrieved {len(threads)} threads:")
    format_digest(results)
