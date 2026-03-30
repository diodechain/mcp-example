# Deployment

Templates in this folder run **`server.py`** from the **project root** (the directory that contains `server.py`, `.venv`, `config.yml`, and `tools/`). Edit the **absolute paths** inside each template to match your clone location.

Unless noted, shell examples use the **project root** as the current directory (the parent of **`deploy/`**).

**Diode configuration precedence** (see **`diode_client/diode_manager.py`**): **code defaults** (same as **`.env_example`**) → **`<project_root>/.env`** (always read by Python when the file exists) → **process environment** from **systemd** / **launchd** / shell (**last wins**). Do not use **`EnvironmentFile=`** in systemd to load **`.env`** — the app loads that file itself. Use **`Environment=`** (systemd) or extra keys under **`EnvironmentVariables`** (plist) only when you need deployment-specific overrides.

**`config.yml`** lists MCP tools only.

---

## Linux (systemd)

1. Create a venv and install dependencies (from the project root):

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Edit **`deploy/mcp-example.service`**: set **`WorkingDirectory`** and the **`python`** path inside **`ExecStart`** to your project root (same path for both).

3. Optional: set **`DIODE_*`** via **`Environment=`** to override **`.env`** / defaults (see **`.env_example`**). Local MCP and Diode API ports are always ephemeral.

4. Install and start:

   ```bash
   sudo cp deploy/mcp-example.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable mcp-example
   sudo systemctl start mcp-example
   ```

5. Status and logs:

   ```bash
   sudo systemctl status mcp-example
   journalctl -u mcp-example -f
   ```

The unit name comes from the filename (`mcp-example.service` → service **`mcp-example`**). Rename the file if you want a different name.

---

## macOS (launchd)

The template **`mcp-example.plist`** is a **LaunchDaemon**-style job (typically installed for all users). It uses label **`io.diode.mcp-example`**.

1. Create a venv and install dependencies (from the project root), same as Linux.

2. Edit **`deploy/mcp-example.plist`**:
   - **`ProgramArguments`**: first element = absolute path to **`.venv/bin/python`**, second = **`server.py`**.
   - **`WorkingDirectory`**: project root (directory containing `server.py`).
   - **`EnvironmentVariables`**: extend **`PATH`** so the **`diode`** CLI is found (for example add Homebrew or your Diode install directory). Add optional **`DIODE_*`** keys here only to override **`.env`** / defaults (see **`.env_example`**).
   - you can add .env overrides in the plist e.g.:
   ```
   	<dict>
         <key>PATH</key>
         <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
         <key>DIODE_PUBLISH_PORT</key>
         <string>9000</string>
	   </dict>
   ```

3. **LaunchDaemon** (starts at boot, runs as root unless you add **`UserName`** / **`GroupName`** — not included in the template; add those keys if you need a non-root service):

   ```bash
   sudo cp deploy/mcp-example.plist /Library/LaunchDaemons/io.diode.mcp-example.plist
   sudo chown root:wheel /Library/LaunchDaemons/io.diode.mcp-example.plist
   sudo chmod 644 /Library/LaunchDaemons/io.diode.mcp-example.plist
   sudo launchctl bootstrap system /Library/LaunchDaemons/io.diode.mcp-example.plist
   ```

   Unload / stop:

   ```bash
   sudo launchctl bootout system /Library/LaunchDaemons/io.diode.mcp-example.plist
   ```

4. **LaunchAgent** (per-user, runs after login; no `sudo` for install):

   ```bash
   cp deploy/mcp-example.plist ~/Library/LaunchAgents/io.diode.mcp-example.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.diode.mcp-example.plist
   ```

   Unload:

   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/io.diode.mcp-example.plist
   ```

5. **Logs**: this template does not set **`StandardOutPath`** / **`StandardErrorPath`**. Add those keys (paths under **`~/Library/Logs/`** or **`/var/log/`**) if you want file logging; otherwise use **Console.app** and filter by process name **`Python`** or your plist **Label**.

---

## Checklist (all platforms)

- [ ] **`WorkingDirectory`** / project root contains **`server.py`**, **`.venv`**, **`config.yml`**, **`tools/`**, and **`diode_client/`**.
- [ ] Python venv has **`requirements.txt`** installed.
- [ ] **`diode`** is on **`PATH`** for the daemon/agent (set **`PATH`** in the unit/plist if needed).
- [ ] **`DIODE_PUBLISH_PORT`** (or **`DIODE_JOIN_ADDRESS`** for join mode) matches how you want clients to reach the server on Diode (see **`.env_example`**).

For local development, run **`python server.py`** in the foreground instead of using these templates.
