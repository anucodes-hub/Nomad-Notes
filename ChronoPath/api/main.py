import os
import time
import structlog
from fastapi import FastAPI, HTTPException, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Histogram
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from agents.supervisor import SupervisorAgent
from schemas import GenerateRequest, GenerateResponse, FeedbackRequest
from core.auth import get_current_user
import hashlib
import json
import redis.asyncio as aioredis
settings = get_settings()
redis_client = aioredis.from_url(settings.redis_url or "redis://localhost:6379", decode_responses=True)

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.get_logger()

# Metrics
REQUEST_COUNT = Counter('request_count', 'App Request Count', ['method', 'endpoint', 'http_status'])
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Request latency', ['endpoint'])


# Vercel injects the VERCEL=1 environment variable. 
# We set root_path="/api" so FastAPI knows how to route requests properly behind Vercel's rewrite.
is_vercel = os.environ.get("VERCEL") == "1"
app = FastAPI(title=settings.app_name, root_path="/api" if is_vercel else "")

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://chronopath-ai.vercel.app", 
        "https://nomadnotes.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
os.makedirs("media", exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

supervisor = SupervisorAgent()

FastAPIInstrumentor.instrument_app(app)

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    latency = time.perf_counter() - start_time
    
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.url.path).observe(latency)
    
    return response

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
    }

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

from core.db import get_pool

@app.post("/feedback")
async def record_feedback(request: FeedbackRequest, current_user: str = Depends(get_current_user)):
    logger.info("feedback_received", request_id=request.request_id, rating=request.rating)
    pool = await get_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_feedback (user_id, request_id, rating) VALUES ($1, $2, $3)",
                    current_user, request.request_id, request.rating
                )
            return {"status": "success"}
        except Exception as e:
            logger.error("feedback_db_error", error=str(e))
            return {"status": "error", "detail": "Database error"}
    else:
        # DB offline, ignore feedback silently
        return {"status": "ignored", "detail": "Database offline"}

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, current_user: str = Depends(get_current_user)):
    logger.info("generate_request_started", request_id=request.request_id if hasattr(request, 'request_id') else "unknown")
    try:
        payload = request.to_agent_payload()
        payload["user_id"] = current_user
        
        # 1. Global Rate Limiter (Max 12 requests per minute to respect Gemini 15 RPM free tier limit)
        try:
            current_requests = await redis_client.incr("global_requests_minute")
            if current_requests == 1:
                await redis_client.expire("global_requests_minute", 60)
            if current_requests > 12:
                logger.warning("rate_limit_exceeded")
                raise HTTPException(status_code=429, detail="High traffic! To ensure stability on our free tier, please wait 60 seconds before generating a new story.")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("redis_rate_limit_failed", error=str(e))
            
        # 2. Redis Caching Layer (Cache identical requests for 24 hours to save API calls)
        payload_str = json.dumps({
            "lat": payload["lat"],
            "lng": payload["lng"],
            "age": payload.get("age")
        }, sort_keys=True)
        cache_key = f"generate_cache:{hashlib.md5(payload_str.encode()).hexdigest()}"
        
        try:
            cached_res = await redis_client.get(cache_key)
            if cached_res:
                logger.info("cache_hit", key=cache_key)
                return json.loads(cached_res)
        except Exception as e:
            logger.warning("redis_cache_get_failed", error=str(e))
        
        # 3. ADK Generation
        res = await supervisor.execute(payload)
        logger.info("generate_request_completed", place=res.place.name)
        
        # 4. Save to Cache
        try:
            await redis_client.setex(cache_key, 86400, res.model_dump_json())
        except Exception as e:
            logger.warning("redis_cache_set_failed", error=str(e))
            
        return res
    except ValueError as exc:
        logger.error("generate_request_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@app.get("/")
async def get_index():
    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    raise HTTPException(status_code=404, detail="Frontend index.html not found.")

@app.get("/static/{path:path}")
async def get_static(path: str):
    base_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    file_path = os.path.join(base_dir, path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    
    fallback_path = os.path.join("static", path)
    if os.path.exists(fallback_path):
        return FileResponse(fallback_path)
        
    raise HTTPException(status_code=404, detail="File not found.")
