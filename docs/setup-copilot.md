# Setting Up with GitHub Copilot

GitHub Copilot gives the agent access to Claude models (Sonnet, Opus, Haiku) via your existing Copilot subscription, with no separate API billing.

---

## 1. Authenticate with Copilot

Inside the running container:

```bash
make shell
hermes login copilot
```

Follow the device-flow prompt — it opens a browser, you paste the code, and credentials are saved to `hermes-data/.env`.

---

## 2. Switch the agent to Copilot

```bash
make use-copilot                          # defaults to claude-sonnet-4.6
make use-copilot MODEL=claude-opus-4.8    # or any other Copilot-available model
make restart
```

`use-copilot.sh` patches `hermes-data/config.yaml` to point at the Copilot inference endpoint and sets the model.

---

## 3. Verify

```bash
make cli
# type anything — you should get a response within a few seconds
```

Or via the API:

```bash
curl -s -X POST http://127.0.0.1:8643/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(grep HERMES_API_SERVER_KEY hermes-data/.env | cut -d= -f2)" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"ping"}],"max_tokens":20}'
```

---

## Available models

| Model | ID |
|---|---|
| Claude Sonnet 4.6 (default) | `claude-sonnet-4.6` |
| Claude Opus 4.8 | `claude-opus-4.8` |
| Claude Haiku 4.5 | `claude-haiku-4.5` |

Pass any of these to `make use-copilot MODEL=<id>`.

---

## Switching to local inference

```bash
make use-omlx MODEL=mlx-community/Qwen3-1.7B-4bit PORT=8001
make restart
```

See [setup-omlx.md](setup-omlx.md) for the full oMLX setup guide including required config tweaks.
