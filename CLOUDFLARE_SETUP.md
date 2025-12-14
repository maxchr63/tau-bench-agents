# Starting Tau-Bench Agents on ngrok Tunnels (recommended)

## Prerequisites

- `ngrok` CLI installed + authenticated (`ngrok config add-authtoken ...`)
- `uv` package manager
- Project dependencies installed
- **Berkeley GitHub account** - Required for assessments to process correctly. Without it, assessments will remain in "pending" status.

## Option A (recommended): One command (ngrok + controllers)

This starts **two ngrok tunnels** (green + white) and then starts the two AgentBeats controllers with the right `CLOUDRUN_HOST` automatically:

```bash
./scripts/start_ngrok_ctrls.sh
```

It will print public URLs like:

```
https://[random-subdomain].ngrok-free.app
```

## Option B: Manual ngrok tunnels + manual controllers

If you prefer separate terminals, start a tunnel for each controller port:

```bash
# Green controller tunnel (port 8010)
ngrok http 8010

# White controller tunnel (port 8011) - separate terminal, separate web UI port
ngrok http 8011 --web-addr 127.0.0.1:4041
```

Each tunnel will output a URL like `https://...ngrok-free.app`. Use the hostnames (**without** `https://`) to start each controller:

```bash
# Green controller
PORT=8010 HTTPS_ENABLED=true CLOUDRUN_HOST=[green-ngrok-host] ROLE=green uv run python scripts/run_ctrl_normalized.py

# White controller (note the PORT=8011 to avoid port conflict)
PORT=8011 HTTPS_ENABLED=true CLOUDRUN_HOST=[white-ngrok-host] ROLE=white uv run python scripts/run_ctrl_normalized.py
```

### Example

```bash
# Green controller
PORT=8010 HTTPS_ENABLED=true CLOUDRUN_HOST=warm-otter-123.ngrok-free.app ROLE=green uv run python scripts/run_ctrl_normalized.py

# White controller
PORT=8011 HTTPS_ENABLED=true CLOUDRUN_HOST=honest-tuna-456.ngrok-free.app ROLE=white uv run python scripts/run_ctrl_normalized.py
```

## Key Environment Variables

| Variable             | Description                                         |
| -------------------- | --------------------------------------------------- |
| `HTTPS_ENABLED=true` | Adds `https://` prefix to the URL                   |
| `CLOUDRUN_HOST`      | The tunnel hostname (without protocol)              |
| `ROLE`               | `green` or `white`                                  |
| `PORT`               | Controller port (default: 8010, use 8011 for white) |

## Verify

Check the agents are running:

```bash
curl https://[tunnel-url]/status
```

Expected response:

```json
{
  "maintained_agents": 1,
  "running_agents": 1,
  "starting_command": "#!/bin/bash\nuv run python main.py run"
}
```

## Important Notes

1. **Don't include `https://`** in `CLOUDRUN_HOST` - `HTTPS_ENABLED=true` adds it automatically
2. **Use different ports** for each agent to avoid conflicts (8010 for green, 8011 for white)
3. **Tunnel URLs are temporary** - they change each time you restart ngrok
4. **Use a Berkeley GitHub account** - This is essential for assessments to be processed. Without it, assessments will stay in "pending" status indefinitely.
5. `scripts/run_ctrl_normalized.py` also runs each controller from an isolated working directory so two controllers don’t clobber `.ab/agents`, and sanitizes `CLOUDRUN_HOST` so generated agent URLs don’t contain accidental `//to_agent/...` (e.g. if a trailing slash was included).

Now you can simply add them on the v2 UI and test them!
