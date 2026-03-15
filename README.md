# Veracity AI - Growth Intelligence Multi-Agent Decision System

Veracity is an advanced, autonomous multi-agent system built on **LangGraph** and **FastAPI**. It is designed to act as a tireless Growth Intelligence Analyst. Give it a product category, brand, and target URLs, and it will continuously scan the web, scrape competitor pages, analyze Hacker News trends, read Reddit discussions, and synthesize deep-market insights into a persistent vector database (ChromaDB) every 30 seconds.

## 🏗️ System Architecture

The backend is entirely headless and decoupled, designed to easily serve Next.js or React frontends.

### 1. The Main Orchestrator (`src/graphs/veracity_graph.py`)
The `veracity_graph` acts as the main system loop. When invoked, it:
1. **Information Fetcher**: Uses Firecrawl, PyPDF2, and native TXT readers to aggressively ingest all raw source material and website links provided.
2. **Parallel Fan-out**: Immediately triggers **6 distinct sub-agent graphs** to run simultaneously, feeding them the parsed web context.
3. **Compiler & Storage Node**: Waits for all 6 subagents to finish their specialized reports, aggregates them into a comprehensive payload, and natively pushes them into ChromaDB for long-term memory and RAG querying.

### 2. The 6 Specialized Sub-Agents (`src/graphs/*`)
Each sub-graph is its own ReAct-style LLM agent with specific instructions and tools. They extract structured context, dispatch parallel collection tools, and synthesize a final report.

- **Adjacent Market Agent** (`adjacent_node.py`): Finds horizontal tech trends and unseen startup threats outside the user's immediate category using Hacker News and SerpAPI.
- **Competitor Agent** (`competitor_node.py`): Maps the direct competitive landscape, extracts positioning, and builds a real-time SWOT analysis.
- **Market Trend Agent** (`marketing_trend_node.py`): Identifies shifting buyer patterns, emerging market signals, and macro-trends.
- **Pricing Agent** (`pricing_node.py`): Scrapes public pricing pages, Reddit willingness-to-pay discussions, and Meta Ad Library to benchmark pricing strategies.
- **User Voice Agent** (`user_voice_node.py`): Analyzes G2/Capterra reviews, YouTube videos, and community blogs to identify messaging gaps and "real" user sentitment.
- **Win-Loss Agent** (`win_loss_node.py`): Synthesizes deal patterns and feature gaps to explain why deals in this category are won or lost.

### 3. The FastAPI Headless Backend (`app.py`)
The system loop is controlled by a modern asynchronous **FastAPI** layer that exposes several endpoints for frontend integration.

- `POST /api/start`: Accepts the initial payload (`brand`, `category`, `urls`, etc.) and triggers the 30-second continuous `veracity_graph` background loop.
- `POST /api/stop`: Halts the background data collection loop.
- `GET /api/status`: Returns current engine state.
- `GET /api/stream`: A Server-Sent Events (SSE) stream using `sse-starlette` that pushes real-time agent execution logs and data points directly to the frontend.
- `POST /api/rag`: A dedicated endpoint for Retrieval-Augmented Generation. Feed it a `subgraph_context` (e.g. "Pricing") and a `query`, and it will query the ChromaDB history vectors from `persistence_utils.py` and stream back a highly specific answer using Groq LLM.

## ⚙️ Tech Stack & Dependencies
- **Core Framework**: LangChain, LangGraph, Python 3.13
- **LLM Provider**: Groq (`openai/gpt-oss-120b`)
- **Web Scraping & Search**: Firecrawl API, SerpAPI
- **Vector Database**: ChromaDB (Local Directory) + HuggingFace Embeddings (`all-MiniLM-L6-v2`)
- **Backend API**: FastAPI, Uvicorn, SSE-Starlette
- **Dependencies List**: See `pyproject.toml` and `requirements.txt`.

## 🚀 How to Run Locally

### 1. Environment Setup
Create a `.env` file in the root directory and ensure you have the following keys:
```env
GROQ_API_KEY="your_groq_key"
FIRECRAWL_API_KEY="your_firecrawl_key"
SERPAPI_API_KEY="your_serpapi_key"
```

### 2. Install Dependencies
```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Start the Backend Server
```bash
uvicorn app:app --reload --port 8000
```
This will start the FastAPI server on `http://127.0.0.1:8000`. 

### 4. Trigger an Analysis
You can send a POST request to `/api/start` to begin the agent loop:
```bash
curl -X POST "http://127.0.0.1:8000/api/start" \
     -H "Content-Type: application/json" \
     -d '{
           "brand": "Stripe",
           "category": "Payment Processing",
           "query": "How are customer needs shifting globally?",
           "competitors": ["Adyen", "Square"],
           "urls": ["https://stripe.com", "https://adyen.com"],
           "pdf_paths": [],
           "txt_paths": []
         }'
```

Watch the terminal to see the `veracity_graph` spin up its sub-agents, scrape the URLs, hit the SERP tools, and deposit the synthesized reports into the `chroma_db/` folder every 30 seconds!