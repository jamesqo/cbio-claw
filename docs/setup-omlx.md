# Setting Up with oMLX (Local Inference)

oMLX runs LLMs locally on Apple Silicon via the MLX framework and exposes an OpenAI-compatible API. Use this when you want to avoid cloud token costs or need offline operation.

**Requirements:** macOS 15+, Apple Silicon (M1/M2/M3/M4), [Homebrew](https://brew.sh)

---

## 1. Install & start oMLX

```bash
make setup-omlx
```

This installs oMLX via Homebrew, registers it as a launchd service (auto-starts on login), and binds it on `0.0.0.0` so the Docker container can reach it via `host.docker.internal`.

oMLX stores its config at `~/.omlx/settings.json`. Check that file to confirm the port it's bound to:

```bash
python3 -c "import json; print(json.load(open('/Users/$USER/.omlx/settings.json'))['server']['port'])"
```

---

## 2. Pull a model

For a fast local model that doesn't overwhelm the machine, use the 1.7B 4-bit Qwen3 quantization:

```bash
hf download mlx-community/Qwen3-1.7B-4bit
```

Restart oMLX so it discovers the model from the HuggingFace cache, then confirm it's listed:

```bash
brew services restart omlx
curl http://127.0.0.1:8001/v1/models
```

> **Avoid large models for local use.** An 8B model sitting in memory alongside the agent causes repeated `adaptive_prefill_throttle` aborts — oMLX's memory predictor badly overestimates KV-cache requirements for large prompts and kills queued requests. The 1.7B model doesn't trigger this.
>
> To delete a model you no longer need:
> ```bash
> rm -rf ~/.cache/huggingface/hub/models--mlx-community--Qwen3-8B-4bit
> brew services restart omlx
> ```

---

## 3. Switch the agent to oMLX

```bash
make use-omlx MODEL=mlx-community/Qwen3-1.7B-4bit PORT=8001
make restart
```

`use-omlx.sh` patches `hermes-data/config.yaml` (a timestamped backup is created first) and sets `OPENAI_API_KEY=local` in `hermes-data/.env` (oMLX doesn't require auth; Hermes needs a non-empty value).

---

## 4. Additional config changes required

`make use-omlx` handles the basics, but a few extra tweaks are needed for a well-behaved local setup. Apply them directly to `hermes-data/config.yaml` and `~/.omlx/settings.json`.

### a) Switch provider to `custom` and add `enable_thinking: false`

`use-omlx.sh` sets `provider: openai-api`, but that type doesn't forward custom request fields. Change it to `custom` and declare the provider in the `providers` block so Hermes sends `enable_thinking: false` on every call:

```yaml
# hermes-data/config.yaml
model:
  default: mlx-community--Qwen3-1.7B-4bit
  provider: custom                              # ← was openai-api
  base_url: http://host.docker.internal:8001/v1
  api_mode: chat_completions
  context_length: 65536                         # bypasses Hermes's 64K minimum check

providers:
  omlx-local:
    base_url: http://host.docker.internal:8001/v1
    api_key: local
    api_mode: chat_completions
    extra_body:
      enable_thinking: false
```

> `context_length: 65536` is intentionally higher than the model's actual 40,960-token window. Hermes refuses to start with models that report less than 64K context; this override silences that check. The model's real limit still applies at inference time.

### b) Disable Qwen3 thinking mode

Qwen3 has a built-in chain-of-thought mode that generates hundreds of hidden reasoning tokens before each answer, making responses slow. Two changes are needed to fully disable it — config alone isn't enough.

In `hermes-data/config.yaml` under `agent:`:

```yaml
agent:
  reasoning_effort: 'none'
```

In `hermes-data/SOUL.md`, add `/no_think` as the very first line:

```
/no_think

# Hermes Agent Persona
...
```

The `/no_think` token is a Qwen3-specific system-prompt directive that suppresses chain-of-thought entirely. Without it, the model reasons verbosely in visible output even when `reasoning_effort` is `none`.

### c) Disable built-in tools for all platforms

Even with `toolsets: []`, Hermes injects 17 built-in tool definitions (~11K tokens) into every prompt. The `toolsets` key controls add-on toolsets; the built-ins are gated per-platform via `platform_toolsets`. A 1.7B model can't reliably use tools anyway, so stripping them cuts prompt size from ~13K tokens to ~640 and response time from ~80s to ~4s.

In `hermes-data/config.yaml`, find the existing `platform_toolsets:` block (near the bottom of the file) and set `cli` and `api_server` to empty lists:

```yaml
platform_toolsets:
  cli: []               # ← replace "- hermes-cli"
  telegram:
  - hermes-telegram
  # ... other platforms unchanged ...
  api_server: []        # ← add this line
```

### d) Tune oMLX memory settings

oMLX's memory predictor has a known bug where it can vastly overestimate KV-cache requirements and abort requests. Setting an explicit ceiling gives it a fixed target to work against. On a 24 GB machine, 18 GB leaves headroom for the OS, Docker, and other apps.

Edit `~/.omlx/settings.json`:

```json
"memory": {
  "prefill_memory_guard": true,
  "memory_guard_tier": "aggressive",        // ← was "balanced"
  "memory_guard_custom_ceiling_gb": 18.0,   // ← was 0.0; set to ~75% of your RAM
  ...
},
"scheduler": {
  "chunked_prefill": true,                  // ← was false
  ...
}
```

Restart oMLX to apply:

```bash
brew services restart omlx
```

---

## 5. Verify end-to-end

```bash
# oMLX health check
curl http://127.0.0.1:8001/v1/models

# Hermes health check
curl http://127.0.0.1:8643/health

# Round-trip test — should respond in < 10s
curl -s -X POST http://127.0.0.1:8643/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(grep HERMES_API_SERVER_KEY hermes-data/.env | cut -d= -f2)" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"ping"}],"max_tokens":20}'
```

Expected: a response in under 10 seconds with `completion_tokens` under 50.

---

## Switching away from oMLX

```bash
make use-copilot         # defaults to claude-sonnet-4.6
make restart
```

See [setup-copilot.md](setup-copilot.md) for the full Copilot setup guide.

---

## Troubleshooting

### Responses are slow or requests time out

Check the oMLX log:

```bash
tail -20 /opt/homebrew/var/log/omlx.log
```

If you see `adaptive_prefill_throttle` lines, two likely causes:

- **Buggy memory prediction** — make sure `memory_guard_tier` is `"aggressive"` and `memory_guard_custom_ceiling_gb` is set to ~75% of your RAM in `~/.omlx/settings.json`.
- **KV cache accumulation** — after many requests the KV cache can grow to 10–15 GB, pushing the system toward the memory threshold and causing even small requests to abort. Restart oMLX to flush it:

```bash
brew services restart omlx
```

If slowness returns after a long session, this is the most likely cause. A restart takes about 5 seconds.

### Gateway keeps showing `s6-log: fatal: unable to lock ...`

Stale lock file from an unclean container exit. Cosmetic — the gateway still runs — but you can clear it:

```bash
rm -f hermes-data/logs/gateways/default/lock
make restart
```

### `401 Incorrect API key provided: local`

This comes from the Hermes title-generation auxiliary trying to call OpenAI to name the session. It's cosmetic and doesn't affect chat responses.

### oMLX port mismatch

`make setup-omlx` defaults to port 8000, but `~/.omlx/settings.json` may have a different value if oMLX was already configured before. Always check before running `make use-omlx`:

```bash
python3 -c "import json; print(json.load(open('/Users/$USER/.omlx/settings.json'))['server']['port'])"
```
