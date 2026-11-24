
import os
import json
import urllib.request


def generate_ai(system, prompt):

    provider = os.getenv("AI_PROVIDER", "ollama").lower()

    if provider == "demo":
        raise RuntimeError("Online demo mode")

    payload = {
        "model": "qwen2.5:3b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "temperature": 0.15,
            "num_predict": 220,
            "repeat_penalty": 1.2,
            "repeat_last_n": 128
        }
    }

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req, timeout=180) as response:
        result = json.load(response)

    answer = result["message"]["content"].strip()

    return answer, "Ollama AI - Qwen2.5"
