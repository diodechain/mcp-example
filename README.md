# Diode MCP server (reference template)

This repository is the **Diode reference layout** for building and deploying an **HTTP (Streamable HTTP) MCP server** that can **publish on the Diode Network** so clients reach `https://<your-client-id>.diode.link:<PORT>/mcp` (via HTTPS) or `diode://<your-client-id>:<PORT>` (via E2EE) without opening firewall ports.


## Quick start (local)

The server starts the tools and the Diode CLI and publishes the tools via the Diode client address assigned when the system is ran the first time.  By default, it will publish the tools publicly on the Diode client address.  See "Setup your .env..." below.

```bash
curl -Ssf https://diode.io/install.sh | bash # install Diode CLI
cd ~/projects # or whatever your project directory is
git clone git@github.com:diodechain/mcp-example.git
cd mcp-example
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
```

When running this, you should see something like:


### Using it

You can immediately start using this tool via E2EE connections by adding it to a private AI workspace at https://nexus.diode.io - see video:


### Projects using this

- Diode Deployer: get your vibe coded app up and running with secure user connections
  - https://github.com/diodechain/diodedeploy-mcp
- Many others...


## Customize tools and access

### Create a new tool

Open this project in your favorite editor and vibe a new tool in minutes.  Or, manually create a tool using the provided examples in the ./tools directory.  Don't forget to enable the tools by listing them in config.yml.

### Setup your .env to specify publication port etc...

You can copy the .env_example to .env and change the defaults to require private publishing (E2EE only).  Also supports Diode Perimeters so your IT person can manage publication - get the perimeter address from the Diode ZTNA console and set it in the .env.

On startup, watch the logs - the local MCP server URL is ephemerally assigned and is printed on startup and published to the DIODE_PUBLISH_PORT you specify (defaults to 8080).


## Deploy to production

Confirm everything is running and ensure your .env is setup per Quick start and Customize tools and access.

Once it is running how you want it, deploy it to your target system and follow the **./deploy/README.md** to ensure it is long-lived on your target system.  You can override the .env settings in the system-specific deployment service file.


## Diode CLI

- Install: [https://diode.io/download/#cli](https://diode.io/download/#cli)  
  Or: `curl -Ssf https://diode.io/install.sh | bash`
- Put `diode` on `PATH`, or place an executable named `diode` in the **project root** or under **`diode_client/`**.
- On startup, the process prints **local** and (when applicable) **public** MCP URLs when publish succeeds.
- **Diode working directory** for the spawned CLI is **`diode_client/`**; **DB**, **logs**, and other client files are created there (runtime paths are gitignored).

### More Diode info

- [Diode](https://diode.io)
- [Diode Network](https://diodenetwork.io)
- [Diode CLI docs](https://cli.docs.diode.io)


## Requirements etc

Tested on MacOS, Ubuntu, and Raspberry Pi (Debian-based).

Takes ~50MB of RAM, see requirements.txt for python package deps.

### Project layout

| Path | Role |
|------|------|
| **`tools/`** | MCP tool modules (**customize to create your own tools**). |
| **`config.yml`** | List the tools you want to enable. |
| **`deploy/`** | System deployment templates for Linux (.service / systemd) and MacOS (.plist / launchd) - see deploy/README.md |
| **`.env_example`** | **Diode** join/publish environment variables; copy to **`.env`** locally. |
| **`diode_client/`** | `diode_manager.py` (Diode CLI lifecycle), optional local `diode` binary, runtime DB/logs. |
| **`requirements.txt`** | Python deps for the server process. |
| **`server.py`** | aiohttp app, JSON-RPC at `POST /mcp`, tool loading from `config.yml`, always starts Diode. |
| **`example_client/`** | Just a reference - minimal HTTP client to list tools and call a few operations. |

### Example MCP client

Should work with any fast MCP style client.  But, have included a simple client to be explicit:

```bash
pip install httpx   # if not already
# Set MCP_SERVER_URL in example_client/client_example.py to match the port in the server log
.venv/bin/python example_client/client_example.py
```

### Other

- [Model Context Protocol](https://modelcontextprotocol.io)
