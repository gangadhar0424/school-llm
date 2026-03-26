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

    def _representative_text(self, text: str, max_chars: int) -> str:
        """Sample start/middle/end segments for broader document coverage."""
        if len(text) <= max_chars:
            return text

        part = max_chars // 3
        start = text[:part]
        mid_start = max((len(text) // 2) - (part // 2), 0)
        middle = text[mid_start:mid_start + part]
        end = text[-part:]
        return (start + "\n\n" + middle + "\n\n" + end).strip()

    def _representative_text(self, text: str, max_chars: int) -> str:
        """Sample start/middle/end segments for better whole-document coverage."""
        if len(text) <= max_chars:
            return text

        # Include more from the beginning to capture titles/contents.
        part = max_chars // 3
        start = text[:part]

        mid_start = max((len(text) // 2) - (part // 2), 0)
        middle = text[mid_start:mid_start + part]

        end = text[-part:]
        return (start + "\n\n" + middle + "\n\n" + end).strip()
    
    async def generate_short_summary(self, text: str) -> str:
        """
        Generate a concise summary (2-3 paragraphs)
        
        Args:
            text: Full text content to summarize
            
        Returns:
            Short summary
        """
        try:
            max_chars = 10000
            text = self._representative_text(text, max_chars)
            
            summary = await ollama_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Create an accurate short summary in 2-3 paragraphs. "
                            "Preserve chapter/topic names."
                        )
                    },
                    {"role": "user", "content": text}
                ],
                model=self.model,
                temperature=0.2,
                max_tokens=250
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
            max_chars = 15000
            text = self._representative_text(text, max_chars)
            
            summary = await ollama_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Give an accurate detailed summary with clear bullet points. "
                            "Include exact chapter/topic names when present."
                        )
                    },
                    {"role": "user", "content": text}
                ],
                model=self.model,
                temperature=0.2,
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
