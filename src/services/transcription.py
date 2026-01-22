import httpx
import logging
from pathlib import Path
from typing import Optional

from src.config import get_settings

logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for transcribing audio using Groq's Whisper API"""

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.groq_api_key
        self.base_url = "https://api.groq.com/openai/v1"

    async def transcribe_audio(self, audio_path: str) -> Optional[str]:
        """
        Transcribe an audio file to text using Groq's Whisper API.

        Args:
            audio_path: Path to the audio file

        Returns:
            Transcribed text or None if failed
        """
        path = Path(audio_path)
        if not path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return None

        # Telegram voice messages come as .oga, we need to send as .ogg for Groq
        # Map file extensions to proper names that Groq accepts
        extension = path.suffix.lower()
        if extension == ".oga":
            filename = path.stem + ".ogg"
            mime_type = "audio/ogg"
        elif extension == ".opus":
            filename = path.name
            mime_type = "audio/opus"
        else:
            filename = path.name
            mime_type = "audio/ogg"

        try:
            async with httpx.AsyncClient() as client:
                with open(audio_path, "rb") as audio_file:
                    response = await client.post(
                        f"{self.base_url}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files={"file": (filename, audio_file, mime_type)},
                        data={
                            "model": "whisper-large-v3",
                            "language": "es",
                            "response_format": "text",
                        },
                        timeout=60.0,
                    )

                if response.status_code == 200:
                    text = response.text.strip()
                    logger.info(f"Transcribed audio: {text[:100]}...")
                    return text
                else:
                    logger.error(
                        f"Transcription failed: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None


# Singleton instance
_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service
