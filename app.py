import asyncio
import json
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.graphs.veracity_graph import veracity_graph
from src.utils.persistence_utils import retrieve_past_runs
from src.llms.groqllm import GroqLLM

app = FastAPI(title="Veracity Growth Intelligence API")

# Allow requests from the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State for the Background Loop
class AppState:
    is_running: bool = False
    last_run_timestamp: Optional[str] = None
    current_config: Optional[dict] = None
    task: Optional[asyncio.Task] = None

app_state = AppState()
sse_queue = asyncio.Queue()  # Use for pushing real-time events to SSE

# ==============================================================================
# Background Polling Service
# ==============================================================================

async def background_poll_loop():
    """Continuously runs the veracity graph every 30 seconds if is_running=True."""
    print("Background polling loop started.")
    while app_state.is_running:
        if not app_state.current_config:
            await asyncio.sleep(5)
            continue
            
        print(f"[{datetime.now().isoformat()}] Starting Veracity Graph invoke...")
        try:
            # We inject the SSE queue into the state so the graph can push updates if needed.
            run_state = dict(app_state.current_config)
            run_state["sse_queue"] = sse_queue

            # Invoke the LangGraph logic
            result = veracity_graph.invoke(run_state)
            
            app_state.last_run_timestamp = datetime.now().isoformat()
            
            # Send completion event to SSE stream
            await sse_queue.put({
                "type": "loop_completed",
                "timestamp": app_state.last_run_timestamp,
                "message": f"Successfully completed run for category: {run_state.get('category')}"
            })
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] Error in background loop: {e}")
            await sse_queue.put({
                "type": "error",
                "message": f"Graph execution failed: {str(e)}"
            })
            
        # Wait 30 seconds before the next run
        await asyncio.sleep(30)
    print("Background polling loop stopped.")


# ==============================================================================
# API Models
# ==============================================================================

class StartPayload(BaseModel):
    brand: str
    category: str
    query: str
    competitors: List[str]
    urls: List[str]
    pdf_paths: List[str] = []
    txt_paths: List[str] = []

class RagRequest(BaseModel):
    subgraph_context: str  # e.g., "Pricing", "User Voice", "Competitor", "All"
    query: str


# ==============================================================================
# Controller Endpoints
# ==============================================================================

@app.post("/api/start")
async def start_loop(payload: StartPayload):
    """Starts the continuous 30-sec background loop."""
    if app_state.is_running:
        return {"status": "already_running", "message": "The loop is already active."}
    
    app_state.current_config = payload.model_dump()
    app_state.is_running = True
    app_state.task = asyncio.create_task(background_poll_loop())
    
    return {"status": "started", "config": app_state.current_config}


@app.post("/api/stop")
async def stop_loop():
    """Stops the continuous background loop."""
    if not app_state.is_running:
        return {"status": "not_running", "message": "The loop is not currently active."}
    
    app_state.is_running = False
    if app_state.task:
        app_state.task.cancel()
        app_state.task = None
        
    return {"status": "stopped", "message": "Background loop has been stopped."}


@app.get("/api/status")
async def get_status():
    """Returns the current state of the backend."""
    return {
        "is_running": app_state.is_running,
        "last_run_timestamp": app_state.last_run_timestamp,
        "current_target": app_state.current_config.get("category") if app_state.current_config else None
    }


# ==============================================================================
# Streaming Endpoint (SSE)
# ==============================================================================

@app.get("/api/stream")
async def stream_events(request: Request):
    """
    Server-Sent Events endpoint to push real-time updates to the UI.
    Next.js frontend will connect using EventSource.
    """
    async def event_generator():
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
                
            try:
                # Wait for next event from the queue
                event_data = await asyncio.wait_for(sse_queue.get(), timeout=1.0)
                yield {
                    "event": event_data.get("type", "message"),
                    "data": json.dumps(event_data)
                }
            except asyncio.TimeoutError:
                # Send a ping/keep-alive to keep the connection open
                yield {
                    "event": "ping",
                    "data": json.dumps({"timestamp": datetime.now().isoformat()})
                }
                
    return EventSourceResponse(event_generator())


# ==============================================================================
# RAG Chat Endpoint
# ==============================================================================

@app.post("/api/rag")
async def rag_chat(req: RagRequest):
    """
    Performs RAG over ChromaDB using persistence_utils.
    """
    subgraph = req.subgraph_context.strip().lower()
    
    # Map friendly frontend dropdown names to actual ChromaDB graph_name metadata
    graph_mapping = {
        "adjacent market": "adjacent_graph",
        "competitor": "competitor_graph",
        "market trend": "marketing_trend_graph",
        "pricing": "pricing_graph",
        "user voice": "user_voice_graph",
        "win-loss": "win_loss_graph",
        "all": "veracity_graph" # Gets the compiled orchestrator report
    }
    
    target_graph = graph_mapping.get(subgraph, "veracity_graph")
    
    # Semantic Search via Persistence Utils
    raw_results = retrieve_past_runs(
        graph_name=target_graph,
        query=req.query,
        n_results=3
    )
    
    # Extract documents
    context_chunks = [res['document'] for res in raw_results if 'document' in res]
    combined_context = "\n\n---\n\n".join(context_chunks) if context_chunks else "(No explicit relevant past data found in this category.)"
    
    llm = GroqLLM().get_llm(temperature=0.3)
    system_prompt = (
        f"You are a Senior Data Analyst for Veracity Growth Intelligence. "
        f"The user is asking a question specifically focusing on the '{req.subgraph_context}' domain.\n\n"
        f"---- DATABASE KNOWLEDGE (Past Analysis) ----\n"
        f"{combined_context}\n\n"
        f"Answer the user's question directly based primarily on the context above. If the context doesn't have the answer, state that."
    )
    
    messages = [
        ("system", system_prompt),
        ("human", req.query)
    ]
    
    response = llm.invoke(messages)
    
    return {
        "answer": response.content,
        "context_used": len(context_chunks)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
