# Use Case Grading — MSAF

Ein KI-gestütztes CLI-Tool zur parallelen Bewertung und Priorisierung von Use Cases nach drei etablierten Frameworks.

Basiert auf dem [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) und dem offiziellen `concurrent_with_visualization`-Sample.

## Workflow

```
Use Case (Input)
      │
      ▼
 [Dispatcher]
      │
  ┌───┴────────────┐
  │                │                │
  ▼                ▼                ▼
[Multi-Kriterien] [WSJF]         [RICE]
  │                │                │
  └───────┬────────┘                │
          └─────────────────────────┘
                    │
               [Aggregator]
                    │
             [Output-Formatter]
                    │
              Zusammenfassung
```

Die drei Analyse-Agents laufen **parallel** (Fan-out), ihre Ergebnisse werden gesammelt und vom Formatter-Agent zu einer Gesamtempfehlung zusammengefasst (Fan-in).

## Bewertungsframeworks

| Framework | Beschreibung |
|---|---|
| **Multi-Kriterien** | 5-Dimensionen-Score: Business Value, Datenqualität, Technische Integration, Org. Readiness, Change-Management |
| **WSJF** | SAFe-Priorisierung: Cost of Delay / Job Size (Fibonacci-Skala) |
| **RICE** | Product-Priorisierung: (Reach × Impact × Confidence) / Effort |

## Voraussetzungen

- Python 3.11+
- [Graphviz](https://graphviz.org/download/) (`brew install graphviz` auf macOS)
- OpenAI API Key

## Setup

```bash
# 1. Abhängigkeiten installieren
pip install agent-framework python-dotenv

# 2. Umgebungsvariablen setzen
cp .env.example .env
# .env befüllen:
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini
```

## Ausführen

```bash
python3 main.py
```

Beim Start wird automatisch:
- ein **Mermaid-Diagramm** des Workflows in der Konsole ausgegeben
- eine **SVG-Datei** (`workflow.svg`) im Projektordner gespeichert

Danach erscheint der interaktive Prompt:

```
Use Case beschreiben: <Use Case hier eingeben>
```

Das Tool analysiert den Use Case parallel mit allen drei Frameworks und gibt eine strukturierte Gesamtempfehlung aus. Mit `exit` beenden.

## Projektstruktur

```
.
├── main.py          # Haupt-Workflow (Dispatcher, Aggregator, Agents, CLI)
├── .env.example     # Vorlage für Umgebungsvariablen
├── .gitignore
└── README.md
```

## Lizenz

Adapted from Microsoft Agent Framework samples. Copyright (c) Microsoft. All rights reserved.
