# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with:
```
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini  # optional, defaults to gpt-4o-mini
```

## Running

```bash
python main.py
```

This starts an interactive REPL. Type a use case description in German, or `exit`/`quit` to stop. On startup, the workflow graph is exported as `workflow.svg`.

## Architecture

Single-file Python application (`main.py`) implementing a **fan-out/fan-in** grading workflow using the `agent-framework` library (Microsoft, prerelease).

**Workflow pattern:**
1. `DispatchToAnalysts` executor fans out the user's input to three parallel agents
2. Three independent agents evaluate the use case simultaneously using different frameworks:
   - **Multi-Kriterien Agent** — 5-dimension scoring (Business Value, Data Quality, Technical Integration, Org Readiness, Change Management)
   - **WSJF Agent** — Weighted Shortest Job First (SAFe methodology)
   - **RICE Agent** — Reach × Impact × Confidence / Effort
3. `AggregateAndFormat` executor fans in the three results and passes them to a formatter agent
4. Formatter agent produces a final comparison table and recommendation

**Key components:**
- `GradingResults` dataclass — holds intermediate results across the workflow stages
- `build_workflow()` — constructs the `WorkflowBuilder` graph connecting dispatcher → three analysts → aggregator
- All agents call OpenAI; system prompts and responses are in German
