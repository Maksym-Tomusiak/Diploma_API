from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.cors import CORSMiddleware

from controllers import (
    auth_router,
    user_router,
    document_router,
    template_router,
    check_result_router,
)

app = FastAPI(
    title="Diploma API",
    description="API for document formatting verification",
    version="1.0.0",
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


@app.get("/")
def read_root():
    """Redirect root to API documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
