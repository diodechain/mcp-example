"""
Standard MCP Server implementation. Compatible with Python 3.9+.
"""
import json
import uuid
import importlib.util
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response
import yaml

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Session storage (in production, use a proper session store)
sessions: Dict[str, Dict[str, Any]] = {}

# Dynamically loaded tools: {tool_name: {"metadata": {...}, "execute": callable}}
TOOLS: Dict[str, Dict[str, Any]] = {}
TOOL_FUNCTIONS: Dict[str, Callable] = {}


def load_config(config_path: str = "config.yml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def load_tool_module(tool_file: str) -> tuple:
    """
    Dynamically load a tool module from a file path.
    Returns (tool_metadata, execute_function)
    """
    tool_path = Path(tool_file)
    if not tool_path.exists():
        raise FileNotFoundError(f"Tool file not found: {tool_file}")
    
    # Convert file path to module name (e.g. "tools/list_files.py" -> "tools.list_files")
    module_name = tool_path.stem
    spec = importlib.util.spec_from_file_location(module_name, tool_path)
    
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {tool_file}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    
    # Get metadata and execute function
    if not hasattr(module, 'TOOL_METADATA'):
        raise AttributeError(f"Tool module {tool_file} must define TOOL_METADATA")
    if not hasattr(module, 'execute'):
        raise AttributeError(f"Tool module {tool_file} must define execute() function")
    
    return module.TOOL_METADATA, module.execute


def load_tools_from_config(config_path: str = "config.yml"):
    """Load all tools from config.yml."""
    global TOOLS, TOOL_FUNCTIONS
    
    config = load_config(config_path)
    tools_config = config.get("tools", [])
    
    TOOLS = {}
    TOOL_FUNCTIONS = {}
    
    for tool_entry in tools_config:
        tool_file = tool_entry.get("file")
        tool_name = tool_entry.get("name")
        
        if not tool_file or not tool_name:
            logger.warning(f"Skipping invalid tool entry: {tool_entry}")
            continue
        
        try:
            metadata, execute_func = load_tool_module(tool_file)
            
            # Verify the tool name matches
            if metadata.get("name") != tool_name:
                logger.warning(f"Tool name mismatch in {tool_file}. Expected {tool_name}, got {metadata.get('name')}")
            
            TOOLS[tool_name] = metadata
            TOOL_FUNCTIONS[tool_name] = execute_func
            logger.info(f"Loaded tool: {tool_name} from {tool_file}")
            
        except Exception as e:
            logger.error(f"Error loading tool {tool_name} from {tool_file}: {e}")
            continue


# Load tools on module import
load_tools_from_config()


def create_jsonrpc_response(request_id: Any, result: Any = None, error: Optional[Dict] = None) -> Dict:
    """Create a JSON-RPC 2.0 response."""
    response = {
        "jsonrpc": "2.0",
        "id": request_id
    }
    if error:
        response["error"] = error
    else:
        response["result"] = result
    return response


def create_text_content(text: str) -> List[Dict[str, str]]:
    """Create MCP text content format."""
    return [{"type": "text", "text": text}]


async def handle_initialize(request: Request) -> Response:
    """Handle initialize method."""
    try:
        data = await request.json()
        request_id = data.get("id")
        params = data.get("params", {})
        
        # Generate session ID
        session_id = str(uuid.uuid4())
        sessions[session_id] = {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "clientInfo": params.get("clientInfo", {})
        }
        logger.info(f"New session created: {session_id} (client: {params.get('clientInfo', {}).get('name', 'unknown')})")
        logger.info(f"Total sessions after creation: {len(sessions)}")
        logger.debug(f"All session IDs: {list(sessions.keys())}")
        
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Cliffon Strengths Finder",
                "version": "1.0.0"
            }
        }
        
        response_data = create_jsonrpc_response(request_id, result)
        
        logger.debug(f"Sending response with session ID header: {session_id[:8]}...")
        return web.Response(
            text=json.dumps(response_data),
            content_type="application/json",
            headers={"Mcp-Session-Id": session_id}
        )
    except Exception as e:
        return web.Response(
            text=json.dumps(create_jsonrpc_response(
                data.get("id"),
                error={"code": -32603, "message": f"Internal error: {str(e)}"}
            )),
            content_type="application/json",
            status=500
        )


async def handle_tools_list(request: Request) -> Response:
    """Handle tools/list method."""
    try:
        data = await request.json()
        request_id = data.get("id")
        # Try to get session ID (case-insensitive header lookup)
        session_id = request.headers.get("Mcp-Session-Id") or request.headers.get("mcp-session-id") or request.headers.get("MCP-Session-Id")
        
        # Verify session
        if not session_id or session_id not in sessions:
            return web.Response(
                text=json.dumps(create_jsonrpc_response(
                    request_id,
                    error={
                        "code": -32000,
                        "message": "Invalid or missing session. Please call 'initialize' first."
                    }
                )),
                content_type="application/json",
                status=401
            )
        
        # Return list of tools
        tools_list = list(TOOLS.values())
        result = {"tools": tools_list}
        
        response_data = create_jsonrpc_response(request_id, result)
        
        return web.Response(
            text=json.dumps(response_data),
            content_type="application/json",
            headers={"Mcp-Session-Id": session_id}
        )
    except Exception as e:
        return web.Response(
            text=json.dumps(create_jsonrpc_response(
                data.get("id"),
                error={"code": -32603, "message": f"Internal error: {str(e)}"}
            )),
            content_type="application/json",
            status=500
        )


async def handle_tools_call(request: Request) -> Response:
    """Handle tools/call method."""
    try:
        data = await request.json()
        request_id = data.get("id")
        params = data.get("params", {})
        
        # Try to get session ID (case-insensitive header lookup)
        session_id = request.headers.get("Mcp-Session-Id") or request.headers.get("mcp-session-id") or request.headers.get("MCP-Session-Id")
        
        logger.debug(f"Session ID from headers: {session_id}")
        logger.debug(f"All headers: {dict(request.headers)}")
        
        # Verify session
        if not session_id:
            logger.warning(f"No session ID header found. Available headers: {list(request.headers.keys())}")
            logger.debug(f"All request headers: {dict(request.headers)}")
            return web.Response(
                text=json.dumps(create_jsonrpc_response(
                    request_id,
                    error={
                        "code": -32000,
                        "message": "Missing session ID. Please call 'initialize' first to establish a session.",
                        "data": {
                            "hint": "Include 'Mcp-Session-Id' header in your request",
                            "available_headers": list(request.headers.keys())
                        }
                    }
                )),
                content_type="application/json",
                status=401
            )
        
        if session_id not in sessions:
            logger.warning(f"Session ID '{session_id}' not found in sessions.")
            logger.warning(f"Total active sessions: {len(sessions)}")
            if len(sessions) > 0:
                logger.warning(f"Active session IDs: {list(sessions.keys())}")
            else:
                logger.warning("No active sessions found. Client may need to call 'initialize' first.")
            logger.debug(f"Full session ID provided: {session_id}")
            return web.Response(
                text=json.dumps(create_jsonrpc_response(
                    request_id,
                    error={
                        "code": -32000,
                        "message": f"Invalid or expired session. Please call 'initialize' to create a new session.",
                        "data": {
                            "session_id_provided": session_id[:8] + "..." if len(session_id) > 8 else session_id,
                            "active_sessions_count": len(sessions)
                        }
                    }
                )),
                content_type="application/json",
                status=401
            )
        
        logger.info(f"Session validated: {session_id[:8]}...")
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        logger.info(f"Tool call: {tool_name} with args: {arguments}")
        
        # Check if tool exists
        if tool_name not in TOOL_FUNCTIONS:
            return web.Response(
                text=json.dumps(create_jsonrpc_response(
                    request_id,
                    error={"code": -32601, "message": f"Unknown tool: {tool_name}"}
                )),
                content_type="application/json",
                status=400
            )
        
        # Get the tool's execute function and metadata
        execute_func = TOOL_FUNCTIONS[tool_name]
        tool_metadata = TOOLS.get(tool_name, {})
        input_schema = tool_metadata.get("inputSchema", {})
        required_params = input_schema.get("required", [])
        
        # Validate required arguments
        if required_params:
            missing_params = [param for param in required_params if param not in arguments]
            if missing_params:
                return web.Response(
                    text=json.dumps(create_jsonrpc_response(
                        request_id,
                        error={
                            "code": -32602,
                            "message": f"Missing required arguments: {', '.join(missing_params)}",
                            "data": {
                                "required": required_params,
                                "provided": list(arguments.keys()),
                                "missing": missing_params
                            }
                        }
                    )),
                    content_type="application/json",
                    status=400
                )
        
        # Execute the tool with provided arguments
        try:
            # Call execute function with arguments unpacked (empty dict is valid for all-optional params)
            logger.debug(f"Executing tool {tool_name} with arguments: {arguments}")
            result_data = execute_func(**arguments)
            
            # Log the raw result data with full details
            logger.info(f"Tool {tool_name} returned result (type: {type(result_data).__name__})")
            logger.debug(f"Tool {tool_name} raw result: {result_data}")
            
            if isinstance(result_data, dict):
                logger.info(f"Tool {tool_name} result is a dict with keys: {list(result_data.keys())}")
                logger.debug(f"Tool {tool_name} full dict result: {json.dumps(result_data, indent=2)}")
            elif isinstance(result_data, list):
                logger.info(f"Tool {tool_name} result is a list with {len(result_data)} items")
                logger.debug(f"Tool {tool_name} full list result: {json.dumps(result_data, indent=2)}")
            else:
                logger.debug(f"Tool {tool_name} result value: {result_data}")
            
            # Convert result to JSON string for text content
            if isinstance(result_data, (dict, list)):
                result_text = json.dumps(result_data)
            else:
                result_text = str(result_data)
            
            logger.info(f"Tool {tool_name} result as text (length: {len(result_text)} chars): {result_text}")
            
            content = create_text_content(result_text)
            logger.info(f"Tool {tool_name} content structure: {json.dumps(content, indent=2)}")
            
            result = {"content": content}
            logger.info(f"Tool {tool_name} executed successfully. Returning result with {len(content)} content item(s)")
            logger.info(f"Tool {tool_name} full result structure: {json.dumps(result, indent=2)}")
            
        except TypeError as e:
            logger.error(f"TypeError executing tool {tool_name}: {e}")
            # Handle argument type mismatches or missing arguments
            error_msg = str(e)
            if "required" in error_msg.lower() or "missing" in error_msg.lower():
                error_response = create_jsonrpc_response(
                    request_id,
                    error={
                        "code": -32602,
                        "message": f"Invalid arguments: {error_msg}",
                        "data": {
                            "required": required_params,
                            "provided": list(arguments.keys())
                        }
                    }
                )
                logger.debug(f"Returning error response: {json.dumps(error_response, indent=2)}")
                return web.Response(
                    text=json.dumps(error_response),
                    content_type="application/json",
                    status=400
                )
            error_response = create_jsonrpc_response(
                request_id,
                error={"code": -32602, "message": f"Invalid arguments: {error_msg}"}
            )
            logger.debug(f"Returning error response: {json.dumps(error_response, indent=2)}")
            return web.Response(
                text=json.dumps(error_response),
                content_type="application/json",
                status=400
            )
        except Exception as e:
            logger.error(f"Exception executing tool {tool_name}: {e}", exc_info=True)
            error_response = create_jsonrpc_response(
                request_id,
                error={"code": -32603, "message": f"Tool execution error: {str(e)}"}
            )
            logger.debug(f"Returning error response: {json.dumps(error_response, indent=2)}")
            return web.Response(
                text=json.dumps(error_response),
                content_type="application/json",
                status=500
            )
        
        response_data = create_jsonrpc_response(request_id, result)
        logger.debug(f"Final JSON-RPC response: {json.dumps(response_data, indent=2)}")
        
        return web.Response(
            text=json.dumps(response_data),
            content_type="application/json",
            headers={"Mcp-Session-Id": session_id}
        )
    except Exception as e:
        return web.Response(
            text=json.dumps(create_jsonrpc_response(
                data.get("id"),
                error={"code": -32603, "message": f"Internal error: {str(e)}"}
            )),
            content_type="application/json",
            status=500
        )


async def handle_mcp_request(request: Request) -> Response:
    """Main MCP request handler - routes to appropriate method handler."""
    try:
        data = await request.json()
        method = data.get("method")
        request_id = data.get("id")
        
        # Log incoming request
        logger.info(f"Incoming request: method={method}, id={request_id}")
        logger.debug(f"Request headers: {dict(request.headers)}")
        logger.debug(f"Request body: {json.dumps(data, indent=2)}")
        
        if method == "initialize":
            return await handle_initialize(request)
        elif method == "tools/list":
            return await handle_tools_list(request)
        elif method == "tools/call":
            return await handle_tools_call(request)
        else:
            return web.Response(
                text=json.dumps(create_jsonrpc_response(
                    data.get("id"),
                    error={"code": -32601, "message": f"Method not found: {method}"}
                )),
                content_type="application/json",
                status=404
            )
    except json.JSONDecodeError:
        return web.Response(
            text=json.dumps(create_jsonrpc_response(
                None,
                error={"code": -32700, "message": "Parse error"}
            )),
            content_type="application/json",
            status=400
        )
    except Exception as e:
        return web.Response(
            text=json.dumps(create_jsonrpc_response(
                None,
                error={"code": -32603, "message": f"Internal error: {str(e)}"}
            )),
            content_type="application/json",
            status=500
        )


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()
    app.router.add_post("/mcp", handle_mcp_request)
    return app


if __name__ == "__main__":
    import asyncio
    import signal
    import socket

    # Load <project_root>/.env before Diode reads DIODE_* (see diode_manager precedence).
    import diode_client.diode_manager  # noqa: F401

    app = create_app()

    async def _run() -> None:
        runner = web.AppRunner(app)
        await runner.setup()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", 0))
        except OSError as e:
            await runner.cleanup()
            logger.error("Could not bind MCP server: %s", e)
            raise SystemExit(1) from e
        sock.listen(128)
        sock.setblocking(False)
        actual_port = int(sock.getsockname()[1])
        site = web.SockSite(runner, sock)
        await site.start()

        try:
            from diode_client.diode_manager import (
                cleanup_diode,
                configure_mcp_listen_port,
                start_diode_cli,
                validate_diode_environment,
            )

            configure_mcp_listen_port(actual_port)
            env_err = validate_diode_environment()
            if env_err:
                await runner.cleanup()
                logger.error("%s See .env_example.", env_err)
                raise SystemExit(1)
            if not start_diode_cli():
                logger.warning("Diode failed to start; MCP server will run locally only.")
        except SystemExit:
            raise
        except Exception as e:
            logger.warning("Could not start Diode: %s. MCP server will run locally only.", e)

        print("=" * 60, flush=True)
        print(f"MCP server listening on http://127.0.0.1:{actual_port}/mcp", flush=True)
        print("Press Ctrl+C to stop", flush=True)
        print("=" * 60, flush=True)

        stop = asyncio.Event()

        def _on_stop() -> None:
            stop.set()

        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _on_stop)
        except (NotImplementedError, RuntimeError, ValueError):
            pass

        try:
            await stop.wait()
        except asyncio.CancelledError:
            pass
        finally:
            try:
                from diode_client.diode_manager import cleanup_diode

                cleanup_diode()
            except Exception:
                pass
            await runner.cleanup()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
