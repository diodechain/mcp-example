import asyncio
import json
import httpx
from typing import Tuple

# MCP server URL (default server runs on port 8099)
MCP_SERVER_URL = "http://127.0.0.1:8099/mcp"

# Global session ID (will be set after initialization)
session_id = None
request_counter = 0

def parse_sse_response(text: str) -> dict:
    """Parse Server-Sent Events (SSE) format response."""
    # SSE format: lines starting with "data: " contain JSON
    json_data = None
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('data: '):
            json_str = line[6:]  # Remove "data: " prefix
            try:
                json_data = json.loads(json_str)
                break
            except json.JSONDecodeError:
                continue
    return json_data or {}

async def make_mcp_request(method: str, params: dict = None, use_session: bool = True) -> Tuple[dict, httpx.Response]:
    """Make a JSON-RPC request to the MCP server."""
    global request_counter
    request_counter += 1
    
    payload = {
        "jsonrpc": "2.0",
        "id": request_counter,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    
    # Add session ID if we have one and it's not the initialize call
    global session_id
    if use_session and session_id and method != "initialize":
        headers["Mcp-Session-Id"] = session_id
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            MCP_SERVER_URL,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        # Extract session ID from response headers if present
        if "Mcp-Session-Id" in response.headers:
            session_id = response.headers["Mcp-Session-Id"]
        
        # Handle different response content types
        content_type = response.headers.get("content-type", "").lower()
        
        if "text/event-stream" in content_type:
            # Parse SSE format
            response_data = parse_sse_response(response.text)
        else:
            # Try to parse as JSON
            try:
                response_data = response.json()
            except json.JSONDecodeError:
                # If JSON parsing fails, try to parse as SSE anyway
                response_data = parse_sse_response(response.text)
                if not response_data:
                    # Last resort: print what we got for debugging
                    print(f"Debug: Response text (first 500 chars): {response.text[:500]}")
                    print(f"Debug: Content-Type: {content_type}")
                    raise ValueError(f"Could not parse response as JSON or SSE. Content-Type: {content_type}")
        
        return response_data, response

async def initialize_session() -> None:
    """Initialize a session with the MCP server."""
    initialize_params = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {
            "name": "client_example",
            "version": "1.0.0"
        }
    }
    response_data, response = await make_mcp_request("initialize", initialize_params, use_session=False)
    # Session ID should be in response headers
    if "Mcp-Session-Id" in response.headers:
        global session_id
        session_id = response.headers["Mcp-Session-Id"]
        print(f"Session initialized with ID: {session_id[:8]}...")
    return response_data

async def list_tools() -> list:
    """List all available tools from the MCP server."""
    response, _ = await make_mcp_request("tools/list", {})
    if "result" in response and "tools" in response["result"]:
        return response["result"]["tools"]
    return []

async def call_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the MCP server."""
    params = {
        "name": tool_name,
        "arguments": arguments if arguments else {}
    }
    response, _ = await make_mcp_request("tools/call", params)
    return response

def get_tool_result_text(result: dict) -> str:
    """Extract tool result text from MCP response. Returns empty string if error or no content."""
    if "error" in result:
        return ""
    if "result" not in result or "content" not in result["result"]:
        return ""
    content = result["result"]["content"]
    if not content or len(content) == 0:
        return ""
    return content[0].get("text", "")


async def main():
    try:
        print("Connecting to MCP server at", MCP_SERVER_URL)
        
        # Initialize session first
        await initialize_session()
        
        print("-" * 50)
        
        # Enumerate available tools from the server
        print("\n0. Enumerating available tools:")
        tools = await list_tools()
        print(f"Found {len(tools)} tool(s):\n")
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.get('name', 'unknown')}")
            print(f"     Description: {tool.get('description', 'No description')}")
            if "inputSchema" in tool:
                print(f"     Input Schema: {json.dumps(tool['inputSchema'], indent=8)}")
            print()
        
        print("-" * 50)
        
        # Test 1: project_files (list project root)
        print("\n1. Testing project_files tool (project root):")
        result = await call_tool("project_files", {})
        if "error" in result:
            print(f"   Error: {result['error'].get('message', result['error'])}")
        else:
            text = get_tool_result_text(result)
            if text:
                data = json.loads(text)
                if "error" in data:
                    print(f"   Tool error: {data['error']}")
                else:
                    print(f"   Directory: {data.get('directory', '.')}")
                    print(f"   Entries: {data.get('count', 0)}")
                    for entry in data.get("entries", [])[:15]:
                        print(f"   - {entry.get('name')} ({entry.get('type')})")
                    if data.get("count", 0) > 15:
                        print(f"   ... and {data['count'] - 15} more")
            else:
                print("   No content returned")
        
        # Test 2: ad_stats (no filter)
        print("\n2. Testing ad_stats tool:")
        result = await call_tool("ad_stats", {})
        if "error" in result:
            print(f"   Error: {result['error'].get('message', result['error'])}")
        else:
            text = get_tool_result_text(result)
            if text:
                data = json.loads(text)
                summary = data.get("summary", {})
                print(f"   Ad count: {summary.get('ad_count', 0)}")
                print(f"   Total spend (USD): {summary.get('total_spend_usd', 0)}")
                print(f"   Total impressions: {summary.get('total_impressions', 0)}")
                print(f"   Total clicks: {summary.get('total_clicks', 0)}")
                print(f"   Overall CTR %: {summary.get('overall_ctr_pct', 0)}")
                print(f"   Overall CPC (USD): {summary.get('overall_cpc_usd', 0)}")
            else:
                print("   No content returned")
        
        # Test 3: ad_stats with channel filter
        print("\n3. Testing ad_stats tool (channel=Google):")
        result = await call_tool("ad_stats", {"channel": "Google"})
        if "error" in result:
            print(f"   Error: {result['error'].get('message', result['error'])}")
        else:
            text = get_tool_result_text(result)
            if text:
                data = json.loads(text)
                summary = data.get("summary", {})
                print(f"   Ad count: {summary.get('ad_count', 0)}")
                print(f"   Total spend (USD): {summary.get('total_spend_usd', 0)}")
            else:
                print("   No content returned")
        
        print("\n" + "-" * 50)
        print("All tests completed!")
        
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"Error connecting to server: {e}")
        print("Make sure the server is running on", MCP_SERVER_URL)

if __name__ == "__main__":
    asyncio.run(main())
