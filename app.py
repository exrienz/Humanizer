from flask import Flask, request, jsonify, render_template
from werkzeug.exceptions import HTTPException
import ollama
import os
import json
import hmac
import hashlib
import time
import re
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from pathlib import Path

app = Flask(__name__)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SKILLS_DIR = Path(os.getenv("SKILLS_DIR", "skills"))

ollama_client = ollama.Client(host=OLLAMA_BASE_URL)


def load_skills(skills_dir: Path):
    loaded = {}
    if not skills_dir.exists():
        return loaded

    for path in sorted(skills_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        loaded[path.stem] = {"systemPrompt": content}
    return loaded


SKILLS = load_skills(SKILLS_DIR)
DEFAULT_SKILL = "default" if "default" in SKILLS else (next(iter(SKILLS), None))

API_KEY_ENABLED = os.getenv("API_KEY_ENABLED", "false").lower() == "true"
API_KEY = os.getenv("API_KEY", "")
HMAC_SECRET = os.getenv("HMAC_SECRET", "")
HMAC_TIMESTAMP_TOLERANCE = int(os.getenv("HMAC_TIMESTAMP_TOLERANCE", "300"))

def _validate_skill_name(skill: str) -> bool:
    if not skill or not isinstance(skill, str):
        return False
    if len(skill) > 50:
        return False
    if not re.match(r'^[a-zA-Z0-9_-]+$', skill):
        return False
    return True

def _verify_hmac_signature(timestamp: str, body: str, signature: str) -> bool:
    if not HMAC_SECRET:
        return True
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > HMAC_TIMESTAMP_TOLERANCE:
            return False
        payload = f"{timestamp}:{body}"
        expected = hmac.new(HMAC_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except (ValueError, TypeError):
        return False

def _verify_api_key():
    if not API_KEY_ENABLED:
        return True
    provided = request.headers.get("X-API-Key", "")
    return hmac.compare_digest(API_KEY, provided)

FALLBACK_SKILL_PROMPTS = {
    "business": "Rewrite for business communication: direct, natural, and specific. Remove robotic phrasing, hype, filler, and vague claims. Preserve facts and commitments. Return only rewritten text.",
    "creative": "Rewrite with a creative but believable human voice. Keep meaning intact, vary rhythm, remove AI phrasing and cliches, and avoid forced metaphors. Return only rewritten text.",
    "technical": "Rewrite technical text to be precise and natural. Keep terminology, commands, and constraints accurate. Remove AI phrasing, filler, and over-formality. Return only rewritten text.",
    "explain": "Rewrite as a clear human explanation. Keep meaning unchanged, simplify dense phrasing, and remove AI-sounding templates and filler. Return only rewritten text.",
}


def _is_timeout_or_gateway_error(err: Exception) -> bool:
    message = str(err).lower()
    return (
        "524" in message
        or "timeout" in message
        or "timed out" in message
        or "gateway" in message
        or "<!doctype html" in message
    )


def _call_model(system_prompt: str, text: str):
    if LLM_PROVIDER in {"openai", "openai_compatible", "openai-compatible"}:
        return _call_openai_compatible(system_prompt, text)

    return ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Text to rewrite:\n{text}"}
        ],
        options={"num_ctx": 4096}
    )


def _call_openai_compatible(system_prompt: str, text: str):
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER is openai")

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Text to rewrite:\n{text}"}
        ]
    }

    req = urlrequest.Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )

    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as http_error:
        raw = http_error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI-compatible HTTP {http_error.code}: {raw}")
    except URLError as url_error:
        raise RuntimeError(f"OpenAI-compatible request failed: {url_error}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"OpenAI-compatible non-JSON response: {raw[:300]}")

    choices = parsed.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenAI-compatible response missing choices: {parsed}")

    message = (choices[0].get("message") or {}).get("content")
    if not message:
        raise RuntimeError(f"OpenAI-compatible response missing message content: {parsed}")

    return {"message": {"content": message}}


def run_humanize(text: str, skill: str):
    if not text:
        return {"error": "No text provided"}, 400

    if not SKILLS:
        return {"error": "No skills loaded. Add markdown files under the skills directory."}, 500

    if skill not in SKILLS:
        return {"error": f"Unknown skill '{skill}'. Available: {list(SKILLS.keys())}"}, 400

    system_prompt = SKILLS[skill]["systemPrompt"]

    try:
        response = _call_model(system_prompt, text)
        humanized = response["message"]["content"]
        return {"humanized": humanized, "skill": skill}, 200
    except Exception as e:
        if skill in FALLBACK_SKILL_PROMPTS and _is_timeout_or_gateway_error(e):
            try:
                retry_response = _call_model(FALLBACK_SKILL_PROMPTS[skill], text)
                humanized = retry_response["message"]["content"]
                return {"humanized": humanized, "skill": skill, "fallback": True}, 200
            except Exception as retry_error:
                return {
                    "error": "Upstream model timeout (retry failed). Please retry with shorter input.",
                    "details": str(retry_error)
                }, 504

        return {"error": str(e)}, 500


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/v1/skills", methods=["GET"])
def list_skills():
    return jsonify({"skills": list(SKILLS.keys()), "default": DEFAULT_SKILL})


@app.route("/api/v1/humanize", methods=["POST"])
def humanize_v1():
    if not _verify_api_key():
        return jsonify({"error": "Invalid or missing API key"}), 401

    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    skill = data.get("skill", DEFAULT_SKILL)

    if not _validate_skill_name(skill):
        return jsonify({"error": "Invalid skill name"}), 400

    timestamp = request.headers.get("X-Timestamp", "")
    signature = request.headers.get("X-Signature", "")
    body = request.get_data(as_text=True)
    if not _verify_hmac_signature(timestamp, body, signature):
        return jsonify({"error": "Invalid or expired signature"}), 401

    payload, status = run_humanize(text, skill)
    return jsonify(payload), status


@app.route("/humanize", methods=["POST"])
def humanize_legacy():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    skill = data.get("skill", DEFAULT_SKILL)
    payload, status = run_humanize(text, skill)
    return jsonify(payload), status


@app.errorhandler(404)
def handle_404(_error):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("index.html"), 200


@app.errorhandler(Exception)
def handle_exception(error):
    if request.path.startswith("/api/"):
        if isinstance(error, HTTPException):
            return jsonify({"error": error.description}), error.code
        return jsonify({"error": str(error)}), 500
    raise error


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
