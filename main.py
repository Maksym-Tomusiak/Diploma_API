from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

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
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title="Diploma API",
    description="API for document formatting verification",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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