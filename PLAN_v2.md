# Use Case Grader — Containerized Deployment Plan (v2)

## Ziel

Den bestehenden MS Agent Framework Use-Case-Grading-Workflow als eigenständigen Docker-Container deployen, der sich als OpenAI-kompatibles "Modell" in das bestehende OpenWebUI integriert. Die Architektur ist als Gateway mit Workflow-Autodiscovery angelegt — neue Agent-Workflows sind ein Ordner in `agents/`, kein neuer Container.

## Architektur

```
┌───────────────────────────────────────────────────────────────┐
│  Docker Network: localai_default (external, bereits vorhanden) │
│                                                               │
│  ┌──────────────┐       ┌──────────────────────────────────┐  │
│  │  OpenWebUI    │──────▶│  agent-gateway                  │  │
│  │  (local-ai    │       │  (eigener Compose Stack)         │  │
│  │   stack)      │       │                                  │  │
│  │              │       │  FastAPI Gateway (server.py)      │  │
│  │  Connection: │       │  ├─ /v1/models (autodiscovery)   │  │
│  │  http://     │       │  ├─ /v1/chat/completions (router)│  │
│  │  agent-      │       │  ├─ /health                      │  │
│  │  gateway:8088│       │  │                                │  │
│  │              │       │  Workflow Registry                │  │
│  │  Modelle:    │       │  ├─ agents/usecase-grading/      │  │
│  │  - usecase-… │       │  ├─ agents/my-new-agent/         │  │
│  │  - ...       │       │  └─ (neuer Ordner → neues Modell)│  │
│  └──────────────┘       └──────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

> **Migration von v1**: OpenWebUI Connection URL von `http://usecase-grader:8088/v1` auf `http://agent-gateway:8088/v1` ändern.

## Projektstruktur

```
agent-gateway/
├── PLAN_v2.md
├── README.md
├── .env.example
├── .env                       # Echte Keys (in .gitignore)
├── .gitignore
├── docker-compose.yml
├── Dockerfile
├── requirements.txt           # Merged: gateway + alle agents
├── src/
│   ├── __init__.py
│   ├── server.py              # FastAPI Gateway: autodiscovery + routing
│   ├── openai_compat.py       # OpenAI Response/SSE Helpers
│   ├── config.py              # Settings via pydantic-settings + .env
│   └── registry.py            # Workflow-Registry mit autodiscovery
└── agents/
    ├── usecase-grading/       # Bestehender Workflow (migriert aus main.py)
    │   ├── __init__.py
    │   ├── workflow.py        # WORKFLOW_ID, WORKFLOW_NAME, build()
    │   └── main.py            # Bestehende Logik (Agents, Prompts, etc.)
    └── _template/             # Kopiervorlage für neue Agents
        ├── __init__.py
        └── workflow.py
```

## Workflow-Modul Convention

Jeder Ordner in `agents/` (außer `_template`) wird automatisch als Workflow registriert, wenn er eine `workflow.py` mit folgendem Interface exportiert:

```python
# agents/usecase-grading/workflow.py

WORKFLOW_ID = "usecase-grader"           # Model-ID für OpenWebUI
WORKFLOW_NAME = "Use Case Grader"        # Anzeigename
WORKFLOW_DESCRIPTION = "Bewertet AI Use Cases nach Multi-Kriterien, WSJF und RICE"

def build():
    """Erstellt und gibt den MS Agent Framework Workflow zurück."""
    from .main import build_workflow
    return build_workflow()
```

Die `_template/workflow.py` dient als Kopiervorlage:

```python
# agents/_template/workflow.py

WORKFLOW_ID = "my-new-agent"
WORKFLOW_NAME = "My New Agent"
WORKFLOW_DESCRIPTION = "Beschreibung für OpenWebUI"

def build():
    raise NotImplementedError("TODO: Workflow implementieren")
```

## Kernkomponenten

### registry.py — Autodiscovery

```python
# Pseudocode / Konzept

import importlib
from pathlib import Path

class WorkflowRegistry:
    def __init__(self):
        self._workflows: dict[str, dict] = {}  # id → {name, description, build_fn, instance}

    def discover(self):
        """Scannt agents/ und registriert alle gültigen Unterordner."""
        agents_dir = Path(__file__).parent.parent / "agents"
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
                continue
            workflow_file = agent_dir / "workflow.py"
            if not workflow_file.exists():
                continue
            module = importlib.import_module(f"agents.{agent_dir.name}.workflow")
            if hasattr(module, "WORKFLOW_ID") and hasattr(module, "build"):
                self._workflows[module.WORKFLOW_ID] = {
                    "name": module.WORKFLOW_NAME,
                    "description": getattr(module, "WORKFLOW_DESCRIPTION", ""),
                    "build_fn": module.build,
                    "instance": None,  # lazy init
                }

    def get_workflow(self, workflow_id: str):
        entry = self._workflows.get(workflow_id)
        if not entry:
            raise KeyError(f"Workflow '{workflow_id}' nicht gefunden")
        if entry["instance"] is None:
            entry["instance"] = entry["build_fn"]()
        return entry["instance"]

    def list_models(self) -> list[dict]:
        return [
            {"id": wid, "object": "model", "created": 1700000000, "owned_by": "local"}
            for wid in self._workflows
        ]
```

### server.py — Gateway

Schlanker als die aktuelle `server.py` (v1): keine Workflow-Logik, nur Routing.
Auth (`GRADER_API_KEY`), Streaming (fake, Wort für Wort) und `/health` bleiben wie in v1 implementiert.

```python
app = FastAPI()
registry = WorkflowRegistry()
registry.discover()

@app.get("/v1/models")
def list_models():
    return {"object": "list", "data": registry.list_models()}

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    workflow = registry.get_workflow(request.model)
    user_message = extract_last_user_message(request)
    output = await run_workflow(workflow, user_message)
    if request.stream:
        return StreamingResponse(stream_sse(output), media_type="text/event-stream")
    return build_completion_response(output)
```

### openai_compat.py — Format-Helpers

Aus bestehender `server.py` extrahieren:
- `build_completion_response(content, model_id)` → dict im OpenAI-Format
- `_sse_chunk(content, completion_id)` → SSE data-Zeile
- `_sse_done(completion_id)` → SSE Abschluss
- `_stream_response(user_message)` → async Generator für Fake-Streaming
- `extract_last_user_message(request)` → str

### config.py

```python
# pydantic-settings liest .env automatisch
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o-mini"   # bestehender Env-Var-Name beibehalten
    GRADER_API_KEY: str = ""

settings = Settings()
```

## Docker Setup

`Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY agents/ ./agents/
EXPOSE 8088
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8088"]
```

`docker-compose.yml`:

```yaml
services:
  agent-gateway:
    build: .
    container_name: agent-gateway
    env_file: .env
    ports:
      - "127.0.0.1:8088:8088"   # nur für lokales Debugging
    networks:
      - localai_default
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8088/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  localai_default:
    external: true   # existiert bereits im local-ai Stack — kein docker network create nötig
```

## Umsetzungsschritte

1. Neues Repo `agent-gateway/` anlegen, Basis-Dateien (.env.example, .gitignore, requirements.txt)
2. `config.py` — pydantic-settings
3. `openai_compat.py` — SSE/Response-Helpers aus bestehender `server.py` extrahieren
4. `registry.py` — Autodiscovery über `agents/`
5. `src/server.py` — Gateway mit Stub (ohne echte Workflows)
6. Smoke Test: `uvicorn src.server:app --port 8088` → `curl /v1/models` gibt leere Liste
7. `agents/usecase-grading/` — bestehende `main.py` hierher migrieren, `workflow.py` als Adapter
8. `agents/_template/workflow.py` — Kopiervorlage
9. End-to-End Test: `/v1/chat/completions` mit echtem Use Case
10. Docker Setup (Dockerfile + docker-compose.yml)
11. Container-Test: `docker compose up --build` → `curl http://localhost:8088/v1/models`
12. OpenWebUI Connection aktualisieren: `http://agent-gateway:8088/v1`
13. README.md

## Neuen Workflow hinzufügen (nach Setup)

```bash
# 1. Template kopieren
cp -r agents/_template agents/my-agent

# 2. workflow.py ausfüllen (WORKFLOW_ID, WORKFLOW_NAME, build())

# 3. Container restarten
docker compose restart

# 4. In OpenWebUI: neues Modell erscheint automatisch
```

## Offene Entscheidungen

- [x] `/health` Endpoint — implementiert
- [x] Streaming (fake, Wort für Wort) — implementiert in server.py
- [x] Auth via `GRADER_API_KEY` — implementiert
- [ ] Echtes Token-Streaming — hängt davon ab ob Agent Framework das unterstützt
- [ ] Logging: strukturiert (JSON) oder einfach stdout?
- [ ] Registry hot-reload (ohne Container-Restart)?
