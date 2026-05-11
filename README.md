# Humanizer

Humanizer is a Flask app that rewrites AI-generated text into more natural human writing using either an Ollama provider or an OpenAI-compatible provider.

Unlike hardcoded prompts, this app loads rewrite instructions from Markdown skill files in `skills/`, inspired by the methodology from `blader/humanizer`.

## Features

- Skill-driven rewriting (`default`, `business`, `creative`, `technical`, `explain`)
- API endpoint for programmatic use
- Simple web UI with skill selection
- Configurable provider, model, and endpoint via environment variables

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Server starts on `http://localhost:8000`.

## Environment variables

### Common

- `LLM_PROVIDER` (default: `ollama`)  
  Supported values: `ollama`, `openai`, `openai_compatible`, `openai-compatible`
- `SKILLS_DIR` (default: `skills`)

### Ollama provider (`LLM_PROVIDER=ollama`)

- `OLLAMA_MODEL` (default: `gemma4:31b-cloud`)
- `OLLAMA_BASE_URL` (default: `https://ollama.com`)
- `OLLAMA_API_KEY` (optional, required for authenticated endpoints)

### OpenAI-compatible provider (`LLM_PROVIDER=openai`)

- `OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)
- `OPENAI_MODEL` (default: `gpt-4o-mini`)
- `OPENAI_API_KEY` (required)

The OpenAI-compatible mode calls `POST {OPENAI_BASE_URL}/chat/completions` using standard OpenAI Chat Completions schema.

## Provider setup examples

### Ollama

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=https://ollama.com
export OLLAMA_MODEL=gemma4:31b-cloud
python app.py
```

### OpenAI-compatible

```bash
export LLM_PROVIDER=openai
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
export OPENAI_API_KEY=your_api_key_here
python app.py
```

## Skill system

Skills are plain `.md` files loaded at startup from `SKILLS_DIR`.

- File name becomes skill name (for example `skills/business.md` => `business`)
- File contents become the system prompt

Add or edit skill files to change behavior without editing application code.

## API

### List skills

```bash
curl http://localhost:8000/api/v1/skills
```

### Humanize text with a selected skill

```bash
curl -X POST http://localhost:8000/api/v1/humanize \
  -H "Content-Type: application/json" \
  -d '{"text":"The implementation is currently underway.","skill":"business"}'
```

Legacy endpoint `/humanize` is also supported.

## Security

Two optional security layers can be enabled to protect the API.

### API Key Authentication

Enable by setting `API_KEY_ENABLED=true` and providing a secret key:

```bash
export API_KEY_ENABLED=true
export API_KEY=your-secret-api-key
python app.py
```

When enabled, include the key in requests:

```bash
curl -X POST http://localhost:8000/api/v1/humanize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{"text":"The implementation is currently underway.","skill":"business"}'
```

Invalid or missing keys return `401 Unauthorized`.

### HMAC Signature Verification

Enable by setting `HMAC_SECRET` (timestamp tolerance is configurable, defaults to 300 seconds):

```bash
export HMAC_SECRET=your-hmac-secret
export HMAC_TIMESTAMP_TOLERANCE=300
python app.py
```

When enabled, requests must include:
- `X-Timestamp`: Unix timestamp of the request
- `X-Signature`: HMAC-SHA256 signature of `{timestamp}:{raw_body}`

Example signature generation in Python:

```python
import hmac
import hashlib
import time
import json

timestamp = str(int(time.time()))
body = json.dumps({"text": "The implementation is underway.", "skill": "business"})
payload = f"{timestamp}:{body}"
signature = hmac.new(b"your-hmac-secret", payload.encode(), hashlib.sha256).hexdigest()
```

Send the signed request:

```bash
curl -X POST http://localhost:8000/api/v1/humanize \
  -H "Content-Type: application/json" \
  -H "X-Timestamp: $timestamp" \
  -H "X-Signature: $signature" \
  -d "$body"
```

Invalid, expired, or tampered signatures return `401 Unauthorized`.

### Security Features

- **Skill name validation**: Blocks path traversal (`../`), null bytes, and special characters. Only `[a-zA-Z0-9_-]` allowed, max 50 chars.
- **Both disabled by default**: Set environment variables to enable.
- **Backward compatible**: When disabled, the API works as before.

## Testing

The project has no dedicated test suite yet, but you can run these checks:

```bash
# Syntax check
python -m py_compile app.py

# Health endpoint (after starting app)
curl http://localhost:8000/health
```
