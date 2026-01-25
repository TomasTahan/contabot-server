import httpx
import logging
from pathlib import Path
from typing import Optional
import tempfile
import os

from src.config import get_settings

logger = logging.getLogger(__name__)


class TelegramService:
    """Service for interacting with Telegram API"""

    def __init__(self):
        settings = get_settings()
        self.token = settings.telegram_bot_token
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Send a text message to a chat. Returns the sent message or None on failure."""
        try:
            async with httpx.AsyncClient() as client:
                data = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                }
                if reply_to_message_id:
                    data["reply_to_message_id"] = reply_to_message_id

                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json=data,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        return result.get("result")  # Returns the Message object
                    return None
                else:
                    logger.error(f"Failed to send message: {response.text}")
                    return None

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None

    async def download_file(self, file_id: str) -> Optional[str]:
        """
        Download a file from Telegram and save it to a temp location.

        Args:
            file_id: Telegram file ID

        Returns:
            Path to the downloaded file or None if failed
        """
        try:
            async with httpx.AsyncClient() as client:
                # Get file path
                response = await client.get(
                    f"{self.base_url}/getFile",
                    params={"file_id": file_id},
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"Failed to get file info: {response.text}")
                    return None

                file_path = response.json()["result"]["file_path"]

                # Download file
                file_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
                response = await client.get(file_url, timeout=60.0)

                if response.status_code != 200:
                    logger.error(f"Failed to download file: {response.status_code}")
                    return None

                # Save to temp file
                suffix = Path(file_path).suffix or ".tmp"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(response.content)
                    logger.info(f"Downloaded file to: {tmp.name}")
                    return tmp.name

        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None

    async def set_webhook(self, webhook_url: str) -> bool:
        """Set the webhook URL for receiving updates"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/setWebhook",
                    json={"url": webhook_url},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        logger.info(f"Webhook set to: {webhook_url}")
                        return True

                logger.error(f"Failed to set webhook: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            return False

    async def delete_webhook(self) -> bool:
        """Delete the current webhook"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/deleteWebhook",
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info("Webhook deleted")
                    return True

                logger.error(f"Failed to delete webhook: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
            return False

    async def get_webhook_info(self) -> dict:
        """Get current webhook information"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/getWebhookInfo",
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json().get("result", {})

                return {}

        except Exception as e:
            logger.error(f"Error getting webhook info: {e}")
            return {}


# Singleton instance
_telegram_service: Optional[TelegramService] = None


def get_telegram_service() -> TelegramService:
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramService()
    return _telegram_service
