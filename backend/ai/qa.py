"""
AI Q&A Module with RAG (Retrieval Augmented Generation)
Answers questions using context from PDF via vector database
"""
import logging
from typing import Dict, List
from config import settings
from vector_db import vector_db
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)

class QASystem:
    """Question-answering system using RAG"""
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL
    
    async def answer_question(self, pdf_url: str, question: str, conversation_history: List[Dict] = None) -> Dict:
        """
        Answer a question using context from PDF
        
        Args:
            pdf_url: URL/identifier of the PDF
            question: User's question
            conversation_history: Previous messages for context
            
        Returns:
            Answer with context and sources
        """
        try:
            # Retrieve only the 2 most relevant chunks to minimize prompt size
            search_results = await vector_db.query_documents(
                pdf_url=pdf_url,
                query=question,
                n_results=2
            )
            
            contexts = search_results.get("documents", [])
            
            if not contexts:
                return {
                    "answer": "I don't have enough context from this PDF to answer that question. Please make sure the PDF has been processed.",
                    "sources": [],
                    "confidence": "low"
                }
            
            # Trim each chunk aggressively — 300 chars max
            trimmed = [ctx[:300] for ctx in contexts]
            context_text = "\n".join([f"[{i+1}] {ctx}" for i, ctx in enumerate(trimmed)])
            
            messages = [
                {"role": "system", "content": "Answer using ONLY the context. Be brief."},
            ]
            
            # Only keep last 1 exchange from history
            if conversation_history:
                messages.extend(conversation_history[-2:])
            
            messages.append({"role": "user", "content": f"{context_text}\n\nQ: {question}"})
            
            answer = await ollama_client.chat(
                messages=messages,
                model=self.model,
                temperature=settings.OLLAMA_TEMPERATURE,
                max_tokens=200
            )
            
            # Determine confidence based on context relevance
            confidence = "high" if len(contexts) >= 3 else "medium" if len(contexts) >= 1 else "low"
            
            logger.info(f"Answered question using {len(contexts)} context chunks")
            
            return {
                "answer": answer,
                "sources": contexts[:3],  # Top 3 relevant chunks
                "confidence": confidence,
                "num_sources": len(contexts)
            }
            
        except Exception as e:
            logger.error(f"Error answering question: {e}")
            raise Exception(f"Failed to answer question: {str(e)}")
    
    async def get_suggested_questions(self, pdf_text_sample: str) -> List[str]:
        """
        Generate suggested questions based on content
        
        Args:
            pdf_text_sample: Sample text from PDF
            
        Returns:
            List of suggested questions
        """
        try:
            # Limit sample length
            max_chars = 5000
            if len(pdf_text_sample) > max_chars:
                pdf_text_sample = pdf_text_sample[:max_chars]
            
            prompt = f"""Based on this educational content, suggest 5 interesting questions a student might ask:

Content:
{pdf_text_sample}

Generate 5 specific, thoughtful questions that would help students understand this material better.
Format: Return only the questions, one per line, without numbering."""
            
            content = await ollama_client.chat(
                messages=[
                    {"role": "system", "content": "You are an educational assistant helping students learn."},
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=300
            )
            questions = [q.strip() for q in content.split("\n") if q.strip()]
            
            logger.info(f"Generated {len(questions)} suggested questions")
            return questions[:5]
            
        except Exception as e:
            logger.error(f"Error generating suggested questions: {e}")
            return []

# Global QA system instance
qa_system = QASystem()
