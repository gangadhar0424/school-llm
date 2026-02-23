"""
AI Audio Generation Module
Generates audio overview using local TTS (pyttsx3)
"""
import asyncio
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from config import settings

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

logger = logging.getLogger(__name__)

class AudioGenerator:
    """Generate audio from text using local TTS"""

    def __init__(self):
        """Initialize audio settings"""
        self.voice = settings.AUDIO_VOICE
        self.rate = settings.AUDIO_RATE
        self.audio_dir = Path(settings.AUDIO_DIR)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_engine(self):
        if pyttsx3 is None:
            raise Exception("pyttsx3 is not installed. Run: pip install pyttsx3")

        engine = pyttsx3.init()
        if self.voice:
            engine.setProperty("voice", self.voice)
        if self.rate:
            engine.setProperty("rate", self.rate)
        return engine

    def _synthesize(self, text: str, file_path: Path):
        engine = self._ensure_engine()
        engine.save_to_file(text, str(file_path))
        engine.runAndWait()

    async def generate_audio(self, text: str, pdf_identifier: str = None) -> Dict:
        """
        Generate audio from text summary

        Args:
            text: Text to convert to speech (summary)
            pdf_identifier: Identifier for the PDF (for filename)

        Returns:
            Dictionary with audio file path and metadata
        """
        try:
            max_chars = 4000
            if len(text) > max_chars:
                text = text[:max_chars] + "..."

            if pdf_identifier:
                hash_obj = hashlib.md5(pdf_identifier.encode())
                filename = f"audio_{hash_obj.hexdigest()}.wav"
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"audio_{timestamp}.wav"

            file_path = self.audio_dir / filename

            if file_path.exists():
                logger.info(f"Audio file already exists: {filename}")
                return {
                    "audio_file": str(file_path),
                    "filename": filename,
                    "duration_estimate": len(text) / 150,
                    "voice": self.voice,
                    "cached": True
                }

            logger.info("Generating audio with local TTS...")
            await asyncio.to_thread(self._synthesize, text, file_path)

            logger.info(f"Audio generated successfully: {filename}")

            return {
                "audio_file": str(file_path),
                "filename": filename,
                "duration_estimate": len(text) / 150,
                "voice": self.voice,
                "cached": False,
                "text_length": len(text)
            }

        except Exception as e:
            logger.error(f"Error generating audio: {e}")
            raise Exception(f"Failed to generate audio: {str(e)}")

    async def generate_audio_from_summary(self, summary: str, pdf_url: str) -> Dict:
        """
        Generate audio overview from summary

        Args:
            summary: Text summary
            pdf_url: PDF URL for identification

        Returns:
            Audio file information
        """
        audio_text = f"Here is an overview of your study material.\n\n{summary}"
        return await self.generate_audio(text=audio_text, pdf_identifier=pdf_url)

    def get_available_voices(self) -> List[str]:
        """Get list of available TTS voices"""
        if pyttsx3 is None:
            return []
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        return [voice.id for voice in voices]

    async def generate_with_custom_voice(self, text: str, voice: str, pdf_identifier: str = None) -> Dict:
        """
        Generate audio with custom voice selection

        Args:
            text: Text to convert
            voice: Voice ID from local TTS engine
            pdf_identifier: PDF identifier

        Returns:
            Audio file information
        """
        available_voices = self.get_available_voices()
        if available_voices and voice not in available_voices:
            raise ValueError("Invalid voice ID for local TTS engine")

        original_voice = self.voice
        self.voice = voice

        try:
            return await self.generate_audio(text, pdf_identifier)
        finally:
            self.voice = original_voice

# Global audio generator instance
audio_generator = AudioGenerator()
