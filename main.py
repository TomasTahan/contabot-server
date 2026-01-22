"""
Main entry point for the Conta Bot server.
"""
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    from src.config import get_settings
    from src.services.telegram import get_telegram_service

    settings = get_settings()
    telegram = get_telegram_service()

    # Set webhook if URL is configured
    if settings.webhook_url:
        webhook_url = f"{settings.webhook_url}/webhook"
        success = await telegram.set_webhook(webhook_url)
        if success:
            logger.info(f"Webhook set to: {webhook_url}")
        else:
            logger.warning("Failed to set webhook")

    logger.info("Conta Bot server started")

    yield

    # Cleanup
    logger.info("Conta Bot server shutting down")


# Create FastAPI app
app = FastAPI(
    title="Conta Bot",
    description="Telegram bot for expense tracking",
    version="1.0.0",
    lifespan=lifespan,
)

# Import and include routers
from src.webhook import router as webhook_router

app.include_router(webhook_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Conta Bot",
        "version": "1.0.0",
        "status": "running",
    }


def main():
    """Run the server."""
    from src.config import get_settings

    settings = get_settings()

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
