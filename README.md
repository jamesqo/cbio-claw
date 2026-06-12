# cbio-claw

A customized deployment of [Hermes Agent](https://get-hermes.ai/) tuned for cBioPortal development work at MSK.

## cbio-claw Action Plan

- [x] Set up local LLM inference (oMLX — see [docs/setup-omlx.md](docs/setup-omlx.md))
- [ ] Set up integrations
  - [ ] Slack
  - [ ] GitHub
  - [x] ClickHouse
  - [ ] Kubernetes
  - [ ] Airflow
  - [ ] others (brainstorm)
- [ ] Deployment
  - (Should work fine with the current setup -- just leave agent on 24/7 on a VPS)

### Discussion points

- [ ] Decide on what functionality an MVP should have, how users will interact with it, etc.
- [ ] Current Docker Compose setup vs. NemoClaw
- [ ] Inside or outside hospital VPN
- [ ] Security considerations
  - [ ] Enabling Tirith
  - [ ] Approval mode
  - [ ] Secret redaction
- [ ] Token usage (probably nbd if running a local LLM)

## Quick Start

### Prerequisites

- Docker + Docker Compose v2
- A Hermes Agent Docker image built either from the [upstream repo](https://github.com/NousResearch/hermes-agent) or pulled from `nousresearch/hermes-agent:v2026.4.16` (pinned to a pre-s6-overlay version)

### 1. Clone

```bash
git clone <this-repo> && cd cbio-claw
```

### 2. Configure Docker Compose Variables

The `docker-compose.env` file is tracked in git with sensible defaults. Edit it to match your system before building:

```bash
# At minimum, set HERMES_UID/HERMES_GID to your `id -u` / `id -g`
```

The `HERMES_DATA` variable in `docker-compose.env` tells Compose where the agent's persistent data lives (config, credentials, state). By default this points to `./hermes-data` — a subdirectory inside the repo (the `.env` file is gitignored, but a `.env.EXAMPLE` template is tracked).

### 3. Create the Runtime Secrets File

The repo ships with a template at `hermes-data/.env.EXAMPLE`. Copy it to `.env` and fill in your API keys:

```bash
cp hermes-data/.env.EXAMPLE hermes-data/.env
```

```bash
# ./hermes-data/.env  — runtime secrets loaded into the containers
# Required
OPENAI_API_KEY=sk-...       # or whichever LLM provider you use
HERMES_API_SERVER_KEY=...   # API key for the gateway server

# Optional but recommended
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
TAVILY_API_KEY=tvly-...
```

> **File permissions note:** The container runs as the `hermes` user, but files it writes to the mounted data volume (`./hermes-data`) need to be owned by *your* host user — otherwise you'd need `sudo` to read or edit them.
>
> The base image handles this by remapping the container's `hermes` user to match your host UID/GID at startup (via `usermod` + `gosu` in the entrypoint). These are set in `docker-compose.env`:
>
> ```bash
> HERMES_UID=501       # Your host UID — run `id -u` to find yours
> HERMES_GID=20        # Your host GID — run `id -g` to find yours
> ```
>
> Change these to match your own user **before** building the image. On macOS/Linux:
> ```bash
> id -u   # → your UID, replace HERMES_UID with this
> id -g   # → your GID, replace HERMES_GID with this
> ```
>
> If you get the UID/GID wrong, you'll see permission-denied errors when trying to read files created by the agent, or the container may fail to chown the data directory on startup.

### 4. Build & Run

```bash
# Build the image for your profile
make build

# Start the gateway (background)
make gateway

# Open an interactive CLI session
make cli

# Start the web dashboard
make dashboard
```

The gateway exposes an OpenAI-compatible API at `http://localhost:8642/v1` by default.

## Makefile Helpers

| Command | Description |
|---------|-------------|
| `make build` | Build the Docker image |
| `make gateway` | Start the gateway daemon |
| `make gateway-logs` | Tail gateway logs |
| `make cli` | Ephemeral interactive chat session |
| `make shell` | Ephemeral bash shell (run `hermes model`, `hermes doctor`, etc.) |
| `make dashboard` | Start the web dashboard |
| `make test` | Run the integration test suite |
| `make down` | Tear down all containers |
| `make setup-omlx` | Install & start oMLX on this Mac (see [setup-omlx.md](docs/setup-omlx.md)) |
| `make use-omlx MODEL=<id>` | Switch agent to a local oMLX model, then `make restart` |
| `make use-copilot` | Switch agent back to GitHub Copilot, then `make restart` |

## Inference backends

| Backend | When to use |
|---|---|
| [oMLX (local)](docs/setup-omlx.md) | No token costs, offline, Apple Silicon Mac |
| [GitHub Copilot](docs/setup-copilot.md) | Cloud models (Claude Sonnet/Opus), existing Copilot subscription |

## Integrations

### Slack

Hermes connects to Slack as a bot. It listens for messages and replies in channels (and optionally threads) that the bot is invited to.

**Setup:**
1. Create a Slack app at https://api.slack.com/apps
2. Enable **Socket Mode** and grant `app_mentions:read`, `chat:write`, and `channels:history` scopes
3. Install the app to your workspace and copy the **Bot Token** (`xoxb-...`) and **App Token** (`xapp-...`)
4. Add them to your data dir `.env` as `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN`

### GitHub

The agent has full `gh` CLI access for interacting with repositories, PRs, issues, and CI.

**Setup:**
1. Authenticate with GitHub: `gh auth login` (inside the container, or mount a pre-authenticated `~/.config/gh/` volume)
2. Or set `GITHUB_TOKEN` in your `.env` file

### ClickHouse

The agent has the `clickhouse-client` CLI installed for querying ClickHouse databases — useful for looking up cBioPortal data warehouse tables, checking pipeline statuses, etc.

**Setup:**
1. Make sure your ClickHouse instance is reachable from the host (the agent will connect from inside the container)
2. Add connection details to your data dir `.env`:
   ```bash
   CLICKHOUSE_HOST=your-clickhouse-host
   CLICKHOUSE_PORT=9000
   CLICKHOUSE_USER=default
   CLICKHOUSE_PASSWORD=...
   CLICKHOUSE_DATABASE=default
   ```
3. The agent can then run queries like `clickhouse-client --host "$CLICKHOUSE_HOST" --query "SELECT ..."`

No additional tool configuration needed — the agent will figure out how to call the CLI based on the environment variables and any hints you give it.
