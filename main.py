from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from core.cleanup import cleanup_old_logs
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from controllers import (
    auth_router,
    user_router,
    document_router,
    template_router,
    check_result_router,
    user_action_log_router,
    font_router,
    analytics_router,
)
from db import SessionLocal
from core.font import ensure_fonts_seeded
from crud.font import FontRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup: ensure fonts are seeded
    logger.info("Starting application...")
    try:
        db = SessionLocal()
        try:
            font_repository = FontRepository(db)
            ensure_fonts_seeded(font_repository)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error during startup font seeding: {e}")
    
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(cleanup_old_logs, args=[30])
        trigger = CronTrigger(day_of_week='mon', hour=3, minute=0)
        scheduler.add_job(cleanup_old_logs, trigger=trigger, args=[30])
        scheduler.start()
        logger.info("Log cleanup scheduler started (Mondays at 3:00 AM + run on start)")
        app.state.scheduler = scheduler
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()
        logger.info("Scheduler shut down.")


app = FastAPI(
    title="Diploma API",
    description="API for document formatting verification",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/api"
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Custom exception handler for validation errors to prevent binary data decoding issues
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom handler for validation errors to safely handle binary data in error messages.
    This prevents UnicodeDecodeError when file uploads fail validation.
    """
    # Process errors and sanitize any binary data
    safe_errors = []
    for error in exc.errors():
        error_dict = dict(error)
        # Remove or sanitize the 'input' field if it contains binary data
        if 'input' in error_dict:
            input_value = error_dict['input']
            if isinstance(input_value, bytes):
                error_dict['input'] = f"<binary data, {len(input_value)} bytes>"
            elif isinstance(input_value, dict):
                # Check for binary data in dict values
                for key, value in input_value.items():
                    if isinstance(value, bytes):
                        input_value[key] = f"<binary data, {len(value)} bytes>"
        safe_errors.append(error_dict)
    
    # Add CORS headers to the error response
    response = JSONResponse(
        status_code=422,
        content={"detail": safe_errors},
    )
    
    # Get origin from request
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response

# CORS middleware configuration
import os

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url and frontend_url not in allowed_origins:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers with /v1 prefix
app.include_router(auth_router, prefix="/v1")
app.include_router(user_router, prefix="/v1")
app.include_router(document_router, prefix="/v1")
app.include_router(template_router, prefix="/v1")
app.include_router(check_result_router, prefix="/v1")
app.include_router(user_action_log_router, prefix="/v1")
app.include_router(font_router, prefix="/v1")
app.include_router(analytics_router, prefix="/v1")


@app.get("/")
def read_root():
    """Redirect root to API documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # You can change the port here if 8000 is taken
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)