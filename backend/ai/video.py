"""
AI Video Generation Module
Generates a script locally using Ollama (no external API keys)
"""
import logging
from typing import Dict
from pathlib import Path
from config import settings
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)

class VideoGenerator:
    """Generate educational videos from text"""
    
    def __init__(self):
        """Initialize video generator"""
        self.video_dir = Path(settings.VIDEO_DIR)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.model = settings.OLLAMA_CHAT_MODEL
    
    async def generate_script(self, summary: str) -> str:
        """
        Generate a video script from summary
        
        Args:
            summary: Text summary to convert to script
            
        Returns:
            Video script
        """
        try:
            prompt = f"""Convert the following educational summary into an engaging video script.

Requirements:
- Clear, conversational tone
- Break into natural speaking segments
- Add appropriate pauses
- Keep it under 2 minutes when spoken
- Make it engaging for students
- Use simple language

Summary:
{summary}

Video Script:"""
            
            script = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "You are an expert educational video scriptwriter."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=800
            )
            logger.info("Generated video script")
            return script
            
        except Exception as e:
            logger.error(f"Error generating script: {e}")
            raise Exception(f"Failed to generate script: {str(e)}")
    
    async def generate_video(self, summary: str) -> Dict:
        """
        Generate video from summary
        
        Args:
            summary: Text summary
            
        Returns:
            Video generation result
        """
        try:
            script = await self.generate_script(summary)
            return {
                "status": "script_only",
                "script": script,
                "message": "Local mode: generated a script only. Use any video tool to render it."
            }
            
        except Exception as e:
            logger.error(f"Error generating video: {e}")
            raise Exception(f"Failed to generate video: {str(e)}")

# Global video generator instance
video_generator = VideoGenerator()
