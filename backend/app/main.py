import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.routes import router
from app.automation.scheduler import start_scheduler, stop_scheduler
from app.config import settings
from app.memory import lt_memory, st_memory
from app.skills import builtin  # noqa: F401 - register built-in skills

logging.basicConfig(level=logging.DEBUG if settings.app_debug else logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting LocalAI Agent backend...")
    try:
        await st_memory.connect()
    except Exception as e:
        logger.warning("Redis unavailable (ST memory disabled): %s", e)
    try:
        lt_memory.connect()
    except Exception as e:
        logger.warning("Qdrant unavailable (LT vector search disabled): %s", e)
    start_scheduler()
    yield
    stop_scheduler()
    await st_memory.disconnect()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="LocalAI Agent",
    description="Multi-Agent automation system with vLLM, CoT reasoning, and skill execution",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "localai-agent"}


@app.get("/", response_class=HTMLResponse)
async def root():
    if (FRONTEND_DIST / "index.html").exists():
        return RedirectResponse("/app")

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LocalAI Agent</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #1a1a1a; color: #ececec; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #212121; border: 1px solid #3a3a3a; border-radius: 12px;
             padding: 40px; max-width: 520px; text-align: center; }}
    h1 {{ color: #d97757; margin-bottom: 8px; }}
    p {{ color: #a0a0a0; line-height: 1.6; }}
    a {{ color: #d97757; text-decoration: none; font-weight: 500; }}
    a:hover {{ text-decoration: underline; }}
    .ports {{ text-align: left; background: #2a2a2a; border-radius: 8px;
              padding: 16px; margin: 20px 0; font-size: 14px; }}
    .ports li {{ margin: 6px 0; }}
    .highlight {{ color: #4ade80; font-weight: 600; }}
    .warn {{ color: #fbbf24; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>LocalAI Agent</h1>
    <p>Backend API is running. This port serves the API, not the chat UI.</p>
    <ul class="ports">
      <li><span class="highlight">Frontend UI → <a href="{settings.frontend_url}">{settings.frontend_url}</a></span></li>
      <li>Backend API → http://localhost:{settings.app_port}/api/v1</li>
      <li>Health check → <a href="/health">/health</a></li>
      <li class="warn">vLLM (port 8000) is LLM inference only — no web UI</li>
    </ul>
    <p>Run <code>./scripts/start_dev.sh</code> to start everything.</p>
  </div>
</body>
</html>""")


# Serve built frontend if available
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
