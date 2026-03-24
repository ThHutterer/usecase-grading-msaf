# Copyright (c) Microsoft. All rights reserved.
# Adapted from:
# https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/visualization/concurrent_with_visualization.py

import asyncio
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from typing_extensions import Never

from agent_framework import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowViz,
    handler,
)
from agent_framework.openai import OpenAIResponsesClient

load_dotenv()

"""
Use Case Grading Workflow
=========================
Fan-out: Use Case → Multi-Kriterien | WSJF | RICE (parallel)
Fan-in:  Alle drei Ergebnisse → Output-Formatter

Basiert auf dem offiziellen concurrent_with_visualization Sample.
"""

# ── System Prompts ─────────────────────────────────────────────────────────────

MULTI_KRITERIEN_INSTRUCTIONS = """Du bist ein AI-Consultant, der Use Cases nach einem 5-Dimensionen-Framework bewertet.

Bewertungsframework (1-10, gewichtet):
1. Business Value (30%): 9-10 = >1M€, 7-8 = 250k-1M€, 5-6 = 50k-250k€, 3-4 = <50k€, 1-2 = unklar
2. Datenqualität (20%): 9-10 = APIs vorhanden, 5-6 = Legacy/Cleansing nötig, 1-2 = nicht vorhanden
3. Technische Integration (20%): 9-10 = Standalone/Cloud, 3-4 = On-premise SAP/Oracle, 1-2 = proprietäres Legacy
4. Org. Readiness (15%): 9-10 = Executive Sponsor + Skills, 3-4 = skeptisch, 1-2 = Widerstand
5. Change-Management (15%): 9-10 = Background-Automatisierung, 3-4 = neue Workflows + Schulung

Ausgabe: strukturierte Bewertung mit Gesamtscore und Empfehlung."""

WSJF_INSTRUCTIONS = """Du bist ein SAFe Program Consultant, der nach WSJF priorisiert.

WSJF = Cost of Delay / Job Size
Cost of Delay = Business Value + Time Criticality + Risk Reduction/OE
Fibonacci-Skala: 1, 2, 3, 5, 8, 13, 21

Ausgabe: WSJF-Tabelle mit Score und Priorität (>10 sofort | 5-10 zeitnah | 2-5 Backlog | <2 zurückstellen)."""

RICE_INSTRUCTIONS = """Du bist ein Product Manager, der nach RICE priorisiert.

RICE = (Reach × Impact × Confidence) / Effort
- Reach: Nutzer pro Quartal
- Impact: 3=Massiv, 2=Hoch, 1=Mittel, 0.5=Niedrig, 0.25=Minimal
- Confidence: 100%/80%/50%
- Effort: Personenmonate

Ausgabe: RICE-Tabelle mit Score und Empfehlung."""

OUTPUT_FORMATTER_INSTRUCTIONS = """Du bekommst drei Priorisierungs-Analysen desselben Use Cases.
Erstelle eine übersichtliche Zusammenfassung mit Vergleichstabelle und einer klaren Gesamt-Empfehlung."""


# ── Dispatcher Executor (Fan-out) ──────────────────────────────────────────────

class DispatchToAnalysts(Executor):
    """Verteilt den Use Case parallel an alle drei Analyse-Agents."""

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        initial_message = Message("user", text=prompt)
        await ctx.send_message(AgentExecutorRequest(messages=[initial_message], should_respond=True))


# ── Aggregator Executor (Fan-in) ───────────────────────────────────────────────

@dataclass
class GradingResults:
    multi_kriterien: str
    wsjf: str
    rice: str


class AggregateAndFormat(Executor):
    """Sammelt die drei Analysen und gibt sie an den Formatter-Agent."""

    def __init__(self, formatter_agent, **kwargs):
        super().__init__(**kwargs)
        self._formatter = formatter_agent

    @handler
    async def aggregate(
        self,
        results: list[AgentExecutorResponse],
        ctx: WorkflowContext[Never, str],
    ) -> None:
        # Ergebnisse nach executor_id mappen
        by_id: dict[str, str] = {}
        for r in results:
            by_id[r.executor_id] = r.agent_response.text

        grading = GradingResults(
            multi_kriterien=by_id.get("multi_kriterien", ""),
            wsjf=by_id.get("wsjf", ""),
            rice=by_id.get("rice", ""),
        )

        # Formatter-Agent fasst die drei Analysen zusammen
        combined = (
            f"## Multi-Kriterien-Analyse\n{grading.multi_kriterien}\n\n"
            f"## WSJF-Analyse\n{grading.wsjf}\n\n"
            f"## RICE-Analyse\n{grading.rice}"
        )
        formatted = await self._formatter.run(combined)
        await ctx.yield_output(formatted)


# ── Workflow Setup ─────────────────────────────────────────────────────────────

def build_workflow():
    client = OpenAIResponsesClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model_id=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    )

    # Drei parallele Analyse-Agents
    multi_kriterien = AgentExecutor(
        client.as_agent(name="multi_kriterien", instructions=MULTI_KRITERIEN_INSTRUCTIONS)
    )
    wsjf = AgentExecutor(
        client.as_agent(name="wsjf", instructions=WSJF_INSTRUCTIONS)
    )
    rice = AgentExecutor(
        client.as_agent(name="rice", instructions=RICE_INSTRUCTIONS)
    )

    # Formatter-Agent für den Aggregator
    formatter = client.as_agent(
        name="formatter", instructions=OUTPUT_FORMATTER_INSTRUCTIONS
    )

    # Executors
    dispatcher = DispatchToAnalysts(id="dispatcher")
    aggregator = AggregateAndFormat(formatter_agent=formatter, id="aggregator")

    # Workflow-Graph: dispatcher → [mk, wsjf, rice] → aggregator
    workflow = (
        WorkflowBuilder(start_executor=dispatcher)
        .add_fan_out_edges(dispatcher, [multi_kriterien, wsjf, rice])
        .add_fan_in_edges([multi_kriterien, wsjf, rice], aggregator)
        .build()
    )

    return workflow


# ── Visualisierung ─────────────────────────────────────────────────────────────

def print_visualization(workflow):
    viz = WorkflowViz(workflow)
    print("\n=== Mermaid ===")
    print(viz.to_mermaid())
    print("\n=== SVG Export ===")
    svg_file = viz.export(filename="workflow", format="svg")
    print(f"SVG gespeichert: {svg_file}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    workflow = build_workflow()

    print_visualization(workflow)

    print("\nUse Case Grading — tippe 'exit' zum Beenden\n")

    while True:
        user_input = input("Use Case beschreiben: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        print("\nAnalysiere parallel (Multi-Kriterien | WSJF | RICE)...\n")

        output = None
        async for event in workflow.run(user_input, stream=True):
            if event.type == "output":
                output = event.data

        if output:
            print(output)
        print("\n" + "─" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
