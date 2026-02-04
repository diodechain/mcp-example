# mcp-example

MCP (Model Context Protocol) server with configurable tools and optional Diode support for publishing the server publicly over TLS.

## Running

```bash
python3 mcp_server.py
```

Server runs at **http://127.0.0.1:8099/mcp** (POST JSON-RPC).

## Configuration

Edit **`config.yml`**:

- **`auto-start-diode`** — Set to `true` to spawn the Diode CLI on startup and publish the MCP port. The public URL (e.g. `https://<client>.diode.link:8099/mcp`) is printed to the console.
- **`tools`** — List of tool modules (file path and tool name). Default tools:
  - **`project_files`** (`tools/file_tool.py`) — List files and directories in the project.
  - **`ad_stats`** (`tools/stats_tool.py`) — Mock advertising stats: ads run, CPC, CPM, CTR, spend, conversions, etc.

## Requirements

- Python 3.9+
- `pip install aiohttp pyyaml`

Validated on macOS and Raspberry Pi 4 (Bullseye).

### Diode (optional)

Only needed if you set **`auto-start-diode: true`** in `config.yml` to publish the MCP server publicly.

- **Install the Diode CLI:** [https://diode.io/download#cli](https://diode.io/download#cli) — pick your OS and follow the instructions so the `diode` binary is on your PATH (or in the project directory).
- The server will spawn the Diode client on startup and print the public URL (e.g. `https://<client>.diode.link:8099/mcp`).

## Project layout

- **`mcp_server.py`** — Main MCP server (HTTP JSON-RPC at `/mcp`).
- **`diode_manager.py`** — Optional Diode CLI integration (start/stop, publish port, print public URL).
- **`config.yml`** — Server config and tool list.
- **`tools/`** — Tool implementations (`file_tool.py`, `stats_tool.py`); each defines `TOOL_METADATA` and `execute()`.
- **`example_client/`** — Example MCP client script (not part of the core server). Run with `python3 example_client/client_example.py` after pointing it at your server URL and adjusting for the tools you expose.

## Integration

Can be used as an MCP server for Cursor, Claude, or other MCP clients. With `auto-start-diode: true`, the server can be reached via the printed Diode public URL (e.g. for remote or shared access).
