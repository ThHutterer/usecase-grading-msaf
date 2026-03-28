# Use Case Grader — Containerized Deployment Plan

## Ziel

Den bestehenden MS Agent Framework Use-Case-Grading-Workflow als eigenständigen Docker-Container deployen, der sich als OpenAI-kompatibles "Modell" in das bestehende OpenWebUI integriert.

## Architektur

```
┌─────────────────────────────────────────────────────┐
│  Docker Network: localai_default (external)         │
│                                                     │
│  ┌──────────────┐       ┌────────────────────────┐  │
│  │  OpenWebUI    │──────▶│  usecase-grader        │  │
│  │  (local-ai    │       │  (eigener Compose      │  │
│  │   stack)      │       │   Stack)               │  │
│  │              │       │                        │  │
│  │  Connection: │       │  FastAPI Server         │  │
│  │  http://     │       │  ├─ /v1/models          │  │
│  │  usecase-    │       │  ├─ /v1/chat/completions│  │
│  │  grader:8088 │       │  └─ MS Agent Framework  │  │
│  └──────────────┘       │      └─ OpenAI API      │  │
│                         └────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Projektstruktur

```
usecase-grading-msaf/
├── PLAN.md
├── README.md
├── .env.example          # OPENAI_API_KEY + OPENAI_MODEL (bereits vorhanden)
├── .env                  # Echte Keys (in .gitignore)
├── .gitignore
├── docker-compose.yml    # neu
├── Dockerfile            # neu
├── requirements.txt      # fastapi + uvicorn hinzufügen
├── main.py               # unverändert (build_workflow() wird importiert)
└── server.py             # neu: FastAPI App mit /v1/chat/completions + /v1/models
```

Keine Umstrukturierung. `server.py` importiert `build_workflow` direkt aus `main.py`.

## Umsetzungsschritte

### 1. Neuen Compose Stack erstellen

`docker-compose.yml`:

```yaml
services:
  usecase-grader:
    build: .
    container_name: usecase-grader
    env_file: .env
    # ports: nur bei lokalem Debugging einkommentieren
    # - "127.0.0.1:8088:8088"
    networks:
      - localai_default

networks:
  localai_default:
    external: true
```

`localai_default` existiert bereits (wird vom local-ai Stack erzeugt, open-webui ist darin). Kein `docker network create` nötig, kein Anpassen des local-ai Stacks.

### 4. Secrets Handling

`.env.example` bleibt unverändert (existiert bereits):

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

`server.py` ruft `load_dotenv()` nicht nochmal auf — das macht bereits `main.py` beim Import. Die Env-Vars `OPENAI_API_KEY` und `OPENAI_MODEL` werden per `env_file` im Compose übergeben.

`requirements.txt` bekommt zwei neue Zeilen:
```
fastapi
uvicorn[standard]
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

### 6. Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py server.py ./

EXPOSE 8088

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8088"]
```

### 7. OpenWebUI Konfiguration

In OpenWebUI Admin Panel → Settings → Connections:

- Neue OpenAI-kompatible Connection hinzufügen
- URL: `http://usecase-grader:8088/v1`
- API Key: beliebig (oder leer, wenn kein Auth am Grader)
- Danach taucht "usecase-grader" als Modell in der Modellauswahl auf

## Reihenfolge beim Bauen mit Claude Code

1. `fastapi` + `uvicorn[standard]` in `requirements.txt` ergänzen
2. `server.py` mit den zwei Endpunkten schreiben (importiert `build_workflow` aus `main.py`)
3. Docker-Setup: `Dockerfile` + `docker-compose.yml`
4. Testen: Port temporär in compose exposen, Container starten, `curl http://localhost:8088/v1/models` muss JSON liefern
5. End-to-End Test: `curl -X POST http://localhost:8088/v1/chat/completions` mit einem Beispiel-Use-Case
6. Port-Expose aus compose entfernen, in OpenWebUI als Connection einrichten und testen (`http://usecase-grader:8088/v1`)
7. README.md schreiben

## Offene Entscheidungen

- [ ] Streaming-Support (SSE) — nice-to-have, nicht zwingend für MVP
- [ ] Health-Check Endpoint (`/health`) für Docker — empfohlen
- [ ] Auth am Grader-Endpunkt — für lokales Netzwerk nicht nötig, für Portfolio aber sauberer
