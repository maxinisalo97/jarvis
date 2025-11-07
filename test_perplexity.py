# test_perplexity.py
import requests
from config import Config

url = "https://api.perplexity.ai/chat/completions"

payload = {
    "model": "sonar",
    "messages": [
        {"role": "user", "content": "Hola, ¿qué día es hoy?"}
    ]
}

headers = {
    "Authorization": f"Bearer {Config.PERPLEXITY_KEY}",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
