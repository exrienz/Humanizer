from flask import Flask, request, jsonify, render_template
import ollama
import os

app = Flask(__name__)

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
ollama_client = ollama.Client(host=OLLAMA_BASE_URL)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/humanize", methods=["POST"])
def humanize():
    data = request.get_json()
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    prompt = f"""Rewrite the following AI-generated text to sound natural, human-written, and authentic.
Make it less formal, add natural imperfections, vary sentence structure, and use colloquial language.
Do not add any commentary, only return the rewritten text.

Text to rewrite:
{text}"""

    try:
        response = ollama_client.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 4096}
        )
        humanized = response["message"]["content"]
        return jsonify({"humanized": humanized})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)