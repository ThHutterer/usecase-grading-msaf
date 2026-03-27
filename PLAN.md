# Use Case Grader — Containerized Deployment Plan

## Ziel

Den bestehenden MS Agent Framework Use-Case-Grading-Workflow als eigenständigen Docker-Container deployen, der sich als OpenAI-kompatibles "Modell" in das bestehende OpenWebUI integriert.

## Architektur

```
┌─────────────────────────────────────────────────────┐
│  Docker Network: ai-services (external, shared)     │
│                                                     │
│  ┌──────────────┐       ┌────────────────────────┐  │
│  │  OpenWebUI    │──────▶│  usecase-grader        │  │
│  │  (local-ai    │       │  (eigener Compose      │  │
│  │   stack)      │       │   Stack)               │  │
│  │              │       │                        │  │
│  │  Connection: │       │  FastAPI Server         │  │
│  │  http://     │       │  ├─ /v1/models          │  │
│  │  usecase-    │       │  ├─ /v1/chat/completions│  │
│  │  grader:8000 │       │  └─ MS Agent Framework  │  │
│  └──────────────┘       │      └─ OpenAI API      │  │
│                         └────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Projektstruktur

```
usecase-grader/
├── PLAN.md
├── README.md
├── .env.example          # Platzhalter für Secrets
├── .env                  # Echte Keys (in .gitignore)
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── server.py         # FastAPI App mit /v1/chat/completions + /v1/models
│   ├── workflow.py        # Bestehender MS Agent Framework Workflow (kopieren/anpassen)
│   └── config.py          # Settings via pydantic-settings + .env
└── tests/
    └── test_server.py     # Smoke test: POST an /v1/chat/completions
```

## Umsetzungsschritte

### 1. Shared Docker Network anlegen

```bash
docker network create ai-services
```

Einmalig auf dem Host ausführen. Beide Compose-Stacks joinen dieses Netzwerk.

### 2. local-ai Stack anpassen

In der bestehenden `docker-compose.yml` des local-ai Stacks das externe Netzwerk hinzufügen:

```yaml
networks:
  ai-services:
    external: true

services:
  open-webui:
    networks:
      - default
      - ai-services
```

### 3. Neuen Compose Stack erstellen

`docker-compose.yml`:

```yaml
services:
  usecase-grader:
    build: .
    container_name: usecase-grader
    env_file: .env
    ports:
      - "8000:8000"   # Optional: nur für lokales Debugging
    networks:
      - ai-services

networks:
  ai-services:
    external: true
```

### 4. Secrets Handling

`.env.example` (kommt ins Repo):

```env
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL_ID=gpt-4o
# Oder Azure OpenAI:
# AZURE_OPENAI_API_KEY=...
# AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
# AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=...
```

`.gitignore`:

```
.env
__pycache__/
*.pyc
```

`config.py` lädt via `pydantic-settings` + `load_dotenv()`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    openai_chat_model_id: str = "gpt-4o"

    class Config:
        env_file = ".env"
```

### 5. FastAPI Server (server.py)

Muss diese zwei Endpunkte implementieren um OpenAI-kompatibel zu sein:

- `GET /v1/models` — Gibt ein Model-Objekt zurück, damit OpenWebUI den Grader als "Modell" anzeigt
- `POST /v1/chat/completions` — Nimmt die User-Message entgegen, führt den Agent Framework Workflow aus, gibt das Ergebnis als ChatCompletion-Response zurück

Der Server muss die OpenAI-API-Response-Struktur exakt einhalten:

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "model": "usecase-grader",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "... Grading-Ergebnis ..."
    },
    "finish_reason": "stop"
  }]
}
```

### 6. Workflow Integration (workflow.py)

Den bestehenden MS Agent Framework Workflow hier reinkopieren/importieren. Anpassungen:

- `agent-framework-core` als Dependency in `requirements.txt` (RC5: `agent-framework-core==1.0.0rc5`)
- Settings aus `config.py` statt hardcoded Keys
- Workflow-Funktion die einen String (User-Input) nimmt und einen String (Grading-Ergebnis) zurückgibt

### 7. Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 8. OpenWebUI Konfiguration

In OpenWebUI Admin Panel → Settings → Connections:

- Neue OpenAI-kompatible Connection hinzufügen
- URL: `http://usecase-grader:8000/v1`
- API Key: beliebig (oder leer, wenn kein Auth am Grader)
- Danach taucht "usecase-grader" als Modell in der Modellauswahl auf

## Reihenfolge beim Bauen mit Claude Code

1. Projektordner + `.env.example` + `.gitignore` anlegen
2. `config.py` mit pydantic-settings
3. `server.py` mit den zwei Endpunkten (erst Stub ohne Workflow)
4. Docker-Setup (Dockerfile + docker-compose.yml)
5. Testen: Container starten, `curl http://localhost:8000/v1/models` muss JSON liefern
6. `workflow.py` — bestehenden Agent Framework Code integrieren
7. End-to-End Test: `curl -X POST http://localhost:8000/v1/chat/completions` mit einem Beispiel-Use-Case
8. Shared Network + local-ai Stack anpassen
9. In OpenWebUI als Connection einrichten und testen
10. README.md schreiben

## Offene Entscheidungen

- [ ] Streaming-Support (SSE) — nice-to-have, nicht zwingend für MVP
- [ ] Health-Check Endpoint (`/health`) für Docker — empfohlen
- [ ] Auth am Grader-Endpunkt — für lokales Netzwerk nicht nötig, für Portfolio aber sauberer
