from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import profile
from app.core import setup_logging
from app.core.config import settings
from app.core.database import init_db
import app.models.db_models  # Import to register models with Base
import uvicorn

# Initialize logging
logger = setup_logging(settings.LOG_LEVEL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    logger.info("Database URL: %s", settings.database_url)
    init_db()
    yield
    # Shutdown logic would go here if needed

app = FastAPI(
    title=settings.APP_NAME,
    description="LLM-orchestrated Multi-Agent System for personalized trip planning",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(profile.router, prefix="/api/profile", tags=["Profile Agent"])




@app.get("/")
def read_root():
    return {"message": "Welcome to Agentic Trip Planner API"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
