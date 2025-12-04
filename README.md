# WorHE 🌍

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Ready](https://img.shields.io/badge/MCP-Ready-green)](https://modelcontextprotocol.io/)

**A narrative graph engine used to generate, track, and visualize fictional worlds using LLMs.**

[History graph viewer](assets/graph.png)

## 📖 Overview

World History Engine is an **MCP (Model Context Protocol) server** designed to be the "backend" for your AI storytelling. Unlike simple text generation, this engine maintains a consistent internal graph database of entities (Factions, Characters, Locations) and their relationships.

It allows Large Language Models (like Claude) to:
1.  **Contextualize:** Query the current state of the world before writing.
2.  **Mutate:** Create new entities or kill existing ones based on narrative events.
3.  **Visualize:** See the world evolve over time with a built-in interactive graph explorer.

## ✨ Key Features

* **🕵️‍♂️ RAG for Fiction:** Keeps track of thousands of entities without filling up the LLM context window.
* **🕸️ Graph-Based Consistency:** Entities have strict relationships (e.g., `Faction A --[war]--> Faction B`).
* **⏳ Time-Travel Debugging:** Includes a web-based visualizer (`world_viz.html`) with a timeline slider. Roll back history to see how the world looked 50 epochs ago.
* **🛠️ Customizable Templates:** Define your own races, biomes, and political systems via simple YAML files.

## 🚀 Quick Start

### Prerequisites
* Python 3.11+
* `uv` (recommended) or `pip`

### Installation

```bash
# Clone the repository
git clone [https://github.com/your-username/world-history-engine.git](https://github.com/your-username/world-history-engine.git)
cd world-history-engine

# Install dependencies
uv sync
````

### Running the graph visualization

```bash
uv run server 
# Then click: http://0.0.0.0:8000
```

### Running the MCP Server manually

```bash
# Run the server with SSE transport (default)
uv run mcp_server.py
```

## 🤖 Using with Claude Desktop or Qwen Desktop

To use this engine as a tool inside Claude, add the following configuration to your `claude_desktop_config.json`:

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

*Note: You may need to specify the absolute path to `mcp_server.py` depending on your setup.*

## 📊 Visualizing Your World

The engine comes with a HTML visualizers.

1.  Generate some history using Claude.
2.  Open `static/world_viz.html` or `static/index.html` (after running `uv run server`) in your browser.
3.  Upload the JSON export of your world (generated via the `get_world_metadata` or export tools).
4.  **Explore:** Drag nodes, filter by factions, and use the **Timeline Slider** at the bottom to replay history.

[Templates AI generator](assets/workbench.png)

## ⚙️ Configuration & Templates

The engine's logic is data-driven. You can modify the simulation rules in `data/templates/`:

  * `factions.yaml`: Define cultures, taboos, and aggression levels.
  * `biomes.yaml`: Configure environmental generation.
  * `resources.yaml`: Manage economy items.

Example `factions.yaml`:

```yaml
- id: fac_human_kingdom
  tags: [honor, monarchy]
  culture:
    aggression: 5
    collectivism: 8
```

## 🏗 Architecture

Here is the internal structure of the world engine entities:

```mermaid
graph TD
    %% --- Стилизация (Styling) ---
    classDef browser fill:#f9f,stroke:#333,stroke-width:2px;
    classDef mcp fill:#ffecb3,stroke:#ff6f00,stroke-width:2px,stroke-dasharray: 5 5;
    classDef storage fill:#e0e0e0,stroke:#333,stroke-width:2px;
    classDef core fill:#e1f5fe,stroke:#0277bd,stroke-width:2px;

    %% --- External Clients ---
    subgraph Clients ["Clients & User Interfaces"]
        BrowserUI[Browser<br>Web Visualizer]:::browser
        ClaudeApp[Claude Desktop<br>AI Assistant]:::mcp
    end

    %% --- Frontend ---
    subgraph Frontend ["Frontend (static/index.html)"]
        direction TB
        UI_Core[App Core]
        
        subgraph JS_Modules ["JS Modules"]
            WB_JS[workbench.js<br>Template Editor]
            SIM_JS[simulation.js<br>Map & Controls]
            CH_JS[chronicles.js<br>History Graph]
        end
        
        API_JS[api.js<br>HTTP Client]
        
        BrowserUI --> UI_Core
        UI_Core --> WB_JS & SIM_JS & CH_JS
        WB_JS & SIM_JS & CH_JS --> API_JS
    end

    %% --- Backend ---
    subgraph Backend ["Backend (Python)"]
        
        %% Entry Points
        subgraph EntryPoints ["Entry Points"]
            Server[server.py<br>FastAPI / HTTP]:::core
            MCPSrv[mcp_server.py<br>MCP Server]:::mcp
        end

        %% Dependency Injection
        DI((Dishka IOC))

        %% Service Layer
        subgraph Services ["Services (Business Logic)"]
            TES[TemplateEditorService]
            SIM_S[SimulationService]
            ST_S[StorytellerService]
            WQS[WorldQueryService]
            NS[NamingService]
        end
        
        %% Core Logic
        subgraph CoreEngine ["Core Engine"]
            WG[WorldGenerator]
            NE[NarrativeEngine]
            Repo[InMemoryRepository]
        end

        %% Connections
        ClaudeApp == Stdio/SSE ==> MCPSrv
        API_JS == HTTP ==> Server
        
        Server & MCPSrv --> DI
        DI --> Services
        
        Services --> CoreEngine
    end

    %% --- Storage ---
    subgraph Storage ["Storage & External"]
        YAML[(YAML Templates<br>data/templates)]:::storage
        JSON[(World JSON<br>world_output)]:::storage
        LLM_API(External LLM API<br>OpenAI/Anthropic):::storage
    end

    %% --- Cross-Links ---
    Services -.-> LLM_API
    Repo -.-> JSON
    TES -.-> YAML
```

## 🗺️ Roadmap

  * [ ] Persistent storage (PostgreSQL/Neo4j support)
  * [ ] Multi-agent simulation steps
  * [ ] Direct export to PDF/Wiki format
  * [ ] Interactive map generation

## 🤝 Contributing

Contributions are welcome\! Please check out the issues tab or submit a PR.

1.  Fork the repository
2.  Create your feature branch (`git checkout -b feature/amazing-feature`)
3.  Commit your changes (`git commit -m 'Add some amazing feature'`)
4.  Push to the branch (`git push origin feature/amazing-feature`)
5.  Open a Pull Request

## 📄 License

This project is licensed under the MIT License.
