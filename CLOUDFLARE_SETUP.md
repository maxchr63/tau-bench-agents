# Starting Tau-Bench Agents on Cloudflare Tunnels

## Prerequisites

- `cloudflared` CLI installed
- `uv` package manager
- Project dependencies installed
- **Berkeley GitHub account** - Required for assessments to process correctly. Without it, assessments will remain in "pending" status.

## Step 1: Start Cloudflare Tunnels

Start a tunnel for each agent on different ports:

```bash
# Green agent tunnel (port 8010)
cloudflared tunnel --url http://localhost:8010

# White agent tunnel (port 8011) - in a separate terminal
cloudflared tunnel --url http://localhost:8011
```

Each tunnel will output a URL like:

```
https://[random-words].trycloudflare.com
```

## Step 2: Start the Agents

Use the tunnel URLs (**without** `https://` prefix) to start each agent:

```bash
# Green agent
HTTPS_ENABLED=true CLOUDRUN_HOST=[green-tunnel-url] ROLE=green uv run agentbeats run_ctrl

# White agent (note the PORT=8011 to avoid port conflict)
PORT=8011 HTTPS_ENABLED=true CLOUDRUN_HOST=[white-tunnel-url] ROLE=white uv run agentbeats run_ctrl
```

### Example

```bash
# Green agent
HTTPS_ENABLED=true CLOUDRUN_HOST=advisor-diary-milk-easter.trycloudflare.com ROLE=green uv run agentbeats run_ctrl

# White agent
PORT=8011 HTTPS_ENABLED=true CLOUDRUN_HOST=slides-electrical-theater-attorney.trycloudflare.com ROLE=white uv run agentbeats run_ctrl
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
3. **Tunnel URLs are temporary** - they change each time you restart cloudflared
4. **Use a Berkeley GitHub account** - This is essential for assessments to be processed. Without it, assessments will stay in "pending" status indefinitely.

Now you can simply add them on the v2 UI and test them!
