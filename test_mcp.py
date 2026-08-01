import subprocess
import json
import sys

def test_mcp():
    mcp_command = ["node", "/Users/admin/Downloads/Nipun/Masai/HandsOn/Live_Projects/chief_of_staff/gmail-mcp-server/dist/index.js"]
    proc = subprocess.Popen(
        mcp_command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # 1. Initialize
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"}
        }
    }
    proc.stdin.write(json.dumps(init_request) + "\n")
    proc.stdin.flush()

    line = proc.stdout.readline()
    print("Init response received.")

    # 2. Initialized notification
    init_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }
    proc.stdin.write(json.dumps(init_notif) + "\n")
    proc.stdin.flush()
    proc.stdout.readline() # Read the response to initialized notification if any

    # 3. Call read_email tool
    call_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "read_email",
            "arguments": {
                "messageId": "19f28b57046055e7"
            }
        }
    }
    proc.stdin.write(json.dumps(call_request) + "\n")
    proc.stdin.flush()

    line = proc.stdout.readline()
    print("Call response:", line)

    # Clean up
    proc.terminate()

if __name__ == "__main__":
    test_mcp()
