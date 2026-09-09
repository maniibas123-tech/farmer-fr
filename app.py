import importlib.util
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Load the required hyphenated configuration filename safely.
CONFIG_PATH = BASE_DIR / "chatbot-config.py"
spec = importlib.util.spec_from_file_location("chatbot_config", CONFIG_PATH)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", config.DEFAULT_MODEL).strip() or config.DEFAULT_MODEL
client = genai.Client(api_key=API_KEY) if API_KEY else None


def clean_history(history):
    """Keep only a small, safe browser-supplied conversation window."""
    if not isinstance(history, list):
        return []
    cleaned = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = item.get("text")
        if role in ("user", "model") and isinstance(text, str) and text.strip():
            cleaned.append({"role": role, "text": text.strip()[:4000]})
    return cleaned


def build_contents(history, message):
    contents = []
    for item in history:
        contents.append(
            types.Content(
                role=item["role"],
                parts=[types.Part.from_text(text=item["text"])],
            )
        )
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=message)],
        )
    )
    return contents


@app.get("/")
def index():
    return render_template("index.html", config=config)


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    history = clean_history(data.get("history", []))

    if not message:
        return jsonify({"error": "Please enter a message."}), 400

    if len(message) > 4000:
        return jsonify({"error": "Please keep your message under 4000 characters."}), 400

    if client is None:
        return jsonify({
            "error": "Gemini API key is not configured. Add GEMINI_API_KEY to .env."
        }), 500

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=build_contents(history, message),
            config=types.GenerateContentConfig(
                system_instruction=config.SYSTEM_PROMPT,
                temperature=0.7,
                max_output_tokens=1000,
            ),
        )
        answer = (response.text or "").strip()
        if not answer:
            answer = "I couldn't generate a response right now. Please try again."
        return jsonify({"reply": answer})
    except Exception as exc:
        print(f"Gemini error: {exc}")
        return jsonify({
            "error": "I couldn't reach Gemini right now. Please check your API key, model name, quota, or try again."
        }), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
