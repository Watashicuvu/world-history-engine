# Alethea 🌍

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Ready](https://img.shields.io/badge/MCP-Ready-green)](https://modelcontextprotocol.io/)

**A narrative graph engine used to generate, track, and visualize fictional worlds using LLMs or purely procedurally.**

[History graph viewer](assets/graph.png)

## 📖 Overview

World History Engine is a narrative framework that can work in two modes:
1.  **AI-Assisted:** As an **MCP Server** for LLMs (like Claude), allowing them to query and mutate the world state consistently.
2.  **Procedural (Standalone):** As a classic generator where you use the GUI or CLI to spawn worlds based on YAML templates, **without needing an API key or LLM**.

It maintains a consistent internal graph database of entities (Factions, Characters, Locations) and their relationships.

## ✨ Key Features

* **🕵️‍♂️ RAG for Fiction:** Keeps track of thousands of entities without filling up the LLM context window.
* **🎲 Dual Mode:** Works with Claude/OpenAI OR as a standalone offline generator.
* **🕸️ Graph-Based Consistency:** Entities have strict relationships (e.g., `Faction A --[war]--> Faction B`).
* **⏳ Time-Travel Debugging:** Includes a web-based visualizer (`world_viz.html`) with a timeline slider. Roll back history to see how the world looked 50 epochs ago.

## 🏗 Architecture

Here is the internal structure of the world engine entities:

```mermaid
graph TD
    %% --- Styles ---
    classDef browser fill:#f9f,stroke:#333,stroke-width:2px;
    classDef mcp fill:#ffecb3,stroke:#ff6f00,stroke-width:2px,stroke-dasharray: 5 5;
    classDef storage fill:#e0e0e0,stroke:#333,stroke-width:2px;
    classDef core fill:#e1f5fe,stroke:#0277bd,stroke-width:2px;

    %% --- Clients ---
    subgraph Clients ["Clients & Interfaces"]
        BrowserUI[Browser<br>Web Visualizer / GUI]:::browser
        ClaudeApp[Claude Desktop<br>AI Assistant]:::mcp
    end

    %% --- Backend ---
    subgraph Backend ["Backend (Python)"]
        
        %% Entry Points
        subgraph EntryPoints ["Entry Points"]
            Server[server.py<br>HTTP API & GUI]:::core
            CLI[main.py<br>CLI Generator]:::core
            MCPSrv[mcp_server.py<br>MCP Server]:::mcp
        end

        DI((Dishka IOC))

        subgraph Services ["Services"]
            TES[TemplateEditorService]
            SIM_S[SimulationService]
            ST_S[StorytellerService]
            WQS[WorldQueryService]
            NS[NamingService]
        end
        
        %% Core Logic
        subgraph CoreEngine ["Core Engine"]
            WG[WorldGenerator]
            Repo[InMemoryRepository]
        end

        %% Connections
        ClaudeApp == Stdio/SSE ==> MCPSrv
        BrowserUI == HTTP ==> Server
        
        Server & MCPSrv & CLI --> DI
        DI --> Services
        Services --> CoreEngine
    end

    %% --- Storage ---
    subgraph Storage ["Storage"]
        YAML[(YAML Templates)]:::storage
        JSON[(World JSON)]:::storage
    end

    Repo -.-> JSON
    TES -.-> YAML
````

## 🚀 Quick Start

### 🐳 Docker Deployment

The recommended way to run the *World History Engine* in both Web UI (8000) and MCP (8001) modes simultaneously is via Docker.

This setup uses **Supervisord** to manage the two distinct processes (`server.py` and `mcp_server.py`) within a single container, offering a robust "all-in-one" solution.

#### 1. Build the Image

Build the container image from the root of your repository:

```bash
docker build -t world-engine-mcp .
````

#### 2\. Run the Container

Run the image, exposing the two required ports:

```bash
docker run -d \
  --name world-engine-instance \
  -p 8000:8000 \
  -p 8001:8001 \
  world-engine-mcp
```

#### 3\. Access

  * **Web UI (Standalone Generation):** Access the graphical interface at `http://localhost:8001`.
  * **MCP Server (AI Integration):** Connect your Claude Desktop or other MCP client to `http://localhost:8000`.
  * **Logs:** View combined logs for both services: `docker logs world-engine-instance`.

### Prerequisites for deployment without Docker

  * Python 3.11+
  * `uv` (recommended) or `pip`

### Installation

```bash
# Clone the repository
git clone [https://github.com/your-username/world-history-engine.git](https://github.com/your-username/world-history-engine.git)
cd world-history-engine

# Install dependencies
uv sync
```

### 🎲 Generating Worlds (Standalone)

You can generate worlds without configuring any AI:

**Option 1: Graphical Interface (GUI)**
Start the web server to generate and visualize worlds interactively.

```bash
uv run server.py
# Open [http://127.0.0.1:8001](http://127.0.0.1:8001) in your browser
```

**Option 2: Command Line (CLI)**
Run the main generation script to create a fresh world snapshot in `world_output/`.

```bash
uv run main.py
```

### 🤖 Running with LLM (MCP Server)

To use this engine as a tool inside Claude (for interactive storytelling), run the MCP server:

```bash
uv run mcp_server.py
```

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "world-engine": {
      "command": "uv",
      "args": [
        "run",
        "mcp_server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

To use this engine as a tool inside Qwen Desktop, paste the following configuration in the MCP settings:
```json
{
    "mcpServers": {
        "world-builder": {
            "url": "http://0.0.0.0:8000"
        }
    }
```
And add [description](system_prompt.md)

## 📊 Visualizing Your World

The engine comes with a standalone HTML visualizer.

1.  Generate a world using **GUI**, **CLI**, or **MCP**.
2.  Open `static/world_viz.html` in your browser.
3.  Upload the JSON export (from `world_output/`).
4.  **Explore:** Drag nodes, filter by factions, and use the **Timeline Slider** to replay history.

## ⚙️ Configuration & Templates

The engine's logic is data-driven. You can modify the simulation rules in `data/templates/`:

  * `factions.yaml`: Define cultures, taboos, and aggression levels.
  * `biomes.yaml`: Configure environmental generation.
  * `resources.yaml`: Manage economy items.

And more other rules of naming in `data/naming`

## 🗺️ Roadmap

  * [ ] Persistent storage (PostgreSQL/Neo4j support)
  * [ ] Multi-agent simulation steps
  * [ ] Direct export to PDF/Wiki format
  * [ ] Interactive map generation

## 🤝 Contributing

Contributions are welcome\! Please check out the issues tab or submit a PR.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.

