"""
Telegram webhook handlers.
"""
import logging
import os
import base64
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from src.agent import get_expense_agent
from src.services.telegram import get_telegram_service
from src.services.transcription import get_transcription_service
from src.services.pocketbase_client import get_pocketbase_service

logger = logging.getLogger(__name__)
router = APIRouter()


class TelegramUser(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None


class TelegramPhoto(BaseModel):
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: Optional[int] = None


class TelegramVoice(BaseModel):
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: Optional[str] = None
    file_size: Optional[int] = None


class TelegramMessage(BaseModel):
    message_id: int
    from_user: Optional[TelegramUser] = Field(default=None, alias="from")
    date: int
    text: Optional[str] = None
    photo: Optional[list[TelegramPhoto]] = None
    voice: Optional[TelegramVoice] = None
    caption: Optional[str] = None

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    update_id: int
    message: Optional[TelegramMessage] = None


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram updates."""
    try:
        body = await request.json()
        logger.info(f"Received update: {body}")

        update = TelegramUpdate.model_validate(body)

        if not update.message:
            return {"ok": True}

        message = update.message
        telegram = get_telegram_service()
        agent = get_expense_agent()
        pb = get_pocketbase_service()

        # Get or create user
        if message.from_user:
            user = await pb.get_or_create_telegram_user(
                telegram_id=str(message.from_user.id),
                name=message.from_user.first_name,
                username=message.from_user.username,
            )

            # Check if user is active
            if not user.active:
                await telegram.send_message(
                    chat_id=message.from_user.id,
                    text="No tienes permisos para usar este bot.",
                )
                return {"ok": True}

        user_id = str(message.from_user.id) if message.from_user else "unknown"
        chat_id = message.from_user.id if message.from_user else None

        # Get display name for the user (username or first_name)
        user_display_name = None
        if message.from_user:
            user_display_name = message.from_user.username or message.from_user.first_name

        if not chat_id:
            return {"ok": True}

        # Process the message
        text_content = ""
        image_base64 = None

        # Handle text messages
        if message.text:
            text_content = message.text

        # Handle voice messages
        if message.voice:
            transcription = get_transcription_service()

            # Download the voice file
            audio_path = await telegram.download_file(message.voice.file_id)
            if audio_path:
                try:
                    # Transcribe
                    transcribed = await transcription.transcribe_audio(audio_path)
                    if transcribed:
                        text_content = transcribed
                        logger.info(f"Transcribed audio: {transcribed}")
                    else:
                        await telegram.send_message(
                            chat_id=chat_id,
                            text="No pude entender el audio. ¿Puedes repetirlo o escribirlo?",
                        )
                        return {"ok": True}
                finally:
                    # Clean up temp file
                    if os.path.exists(audio_path):
                        os.remove(audio_path)

        # Handle photos
        if message.photo:
            # Get the largest photo
            largest_photo = max(message.photo, key=lambda p: p.width * p.height)

            # Download the photo
            photo_path = await telegram.download_file(largest_photo.file_id)
            if photo_path:
                try:
                    # Read and encode as base64
                    with open(photo_path, "rb") as f:
                        image_base64 = base64.b64encode(f.read()).decode("utf-8")

                    # Use caption as text if available
                    if message.caption:
                        text_content = message.caption
                    elif not text_content:
                        text_content = "Recibí esta boleta, ¿qué gasto registro?"

                finally:
                    # Clean up temp file
                    if os.path.exists(photo_path):
                        os.remove(photo_path)

        # If no content, ignore
        if not text_content and not image_base64:
            return {"ok": True}

        # Process with agent
        try:
            response = await agent.process_message(
                text=text_content,
                telegram_user_id=user_id,
                telegram_username=user_display_name,
                image_base64=image_base64,
            )

            # Send response
            await telegram.send_message(
                chat_id=chat_id,
                text=response,
                reply_to_message_id=message.message_id,
            )

        except Exception as e:
            logger.error(f"Error processing message with agent: {e}")
            await telegram.send_message(
                chat_id=chat_id,
                text="Hubo un error procesando tu mensaje. Por favor intenta de nuevo.",
            )

        return {"ok": True}

    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
