import json
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from main import build_workflow

app = FastAPI()
_workflow = None
_security = HTTPBearer(auto_error=False)


def get_workflow():
    global _workflow
    if _workflow is None:
        _workflow = build_workflow()
    return _workflow


def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    required_key = os.getenv("GRADER_API_KEY")
    if not required_key:
        return  # Auth deaktiviert wenn kein Key gesetzt
    if credentials is None or credentials.credentials != required_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Request / Response Models ──────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "usecase-grader"
    messages: list[Message]
    stream: bool = False


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse_chunk(content: str, completion_id: str) -> str:
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "usecase-grader",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _sse_done(completion_id: str) -> str:
    chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "usecase-grader",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"


async def _run_workflow(user_message: str) -> str:
    workflow = get_workflow()
    output = ""
    async for event in workflow.run(user_message, stream=True):
        if event.type == "output":
            data = event.data
            output = data.text if hasattr(data, "text") else str(data)
    return output


async def _stream_response(user_message: str):
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    output = await _run_workflow(user_message)
    # Fake-Streaming: Wort für Wort senden
    words = output.split(" ")
    for i, word in enumerate(words):
        chunk = word if i == len(words) - 1 else word + " "
        yield _sse_chunk(chunk, completion_id)
    yield _sse_done(completion_id)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/models", dependencies=[Depends(verify_auth)])
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "usecase-grader",
                "object": "model",
                "created": 1700000000,
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/chat/completions", dependencies=[Depends(verify_auth)])
async def chat_completions(request: ChatCompletionRequest):
    user_message = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )

    if request.stream:
        return StreamingResponse(
            _stream_response(user_message),
            media_type="text/event-stream",
        )

    output = await _run_workflow(user_message)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "usecase-grader",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": output},
                "finish_reason": "stop",
            }
        ],
    }
