"""
AI Summary Generation Module
Creates short and detailed summaries using Ollama
"""
import logging
from typing import Dict
from config import settings
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)

class SummaryGenerator:
    """Generate summaries from PDF text using Ollama"""
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL
    
    async def generate_short_summary(self, text: str) -> str:
        """
        Generate a concise summary (2-3 paragraphs)
        
        Args:
            text: Full text content to summarize
            
        Returns:
            Short summary
        """
        try:
            # Aggressive limit for CPU speed
            max_chars = 2000
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            summary = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "Summarize in 1-2 short paragraphs."},
                    {"role": "user", "content": text}
                ],
                model=self.model,
                temperature=settings.OLLAMA_TEMPERATURE,
                max_tokens=200
            )
            logger.info("Generated short summary")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating short summary: {e}")
            raise Exception(f"Failed to generate summary: {str(e)}")
    
    async def generate_detailed_summary(self, text: str) -> str:
        """
        Generate a comprehensive detailed summary
        
        Args:
            text: Full text content to summarize
            
        Returns:
            Detailed summary
        """
        try:
            max_chars = 3000
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            summary = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "Give a detailed summary with bullet points."},
                    {"role": "user", "content": text}
                ],
                model=self.model,
                temperature=settings.OLLAMA_TEMPERATURE,
                max_tokens=400
            )
            logger.info("Generated detailed summary")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating detailed summary: {e}")
            raise Exception(f"Failed to generate detailed summary: {str(e)}")
    
    async def generate_both_summaries(self, text: str) -> Dict[str, str]:
        """
        Generate both short and detailed summaries concurrently.
        Running them in parallel cuts total wall-clock time nearly in half.
        """
        import asyncio
        try:
            short_task = asyncio.create_task(self.generate_short_summary(text))
            detailed_task = asyncio.create_task(self.generate_detailed_summary(text))
            short, detailed = await asyncio.gather(short_task, detailed_task)
            
            return {
                "short_summary": short,
                "detailed_summary": detailed
            }
            
        except Exception as e:
            logger.error(f"Error generating summaries: {e}")
            raise

# Global summary generator instance
summary_generator = SummaryGenerator()
