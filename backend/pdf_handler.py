"""
PDF Handler for School LLM
Extracts text from PDFs, chunks content, and prepares for AI processing
"""
import requests
import io
from PyPDF2 import PdfReader
from typing import List, Dict, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class PDFHandler:
    """Handle PDF extraction and processing"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize PDF handler
        
        Args:
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    async def extract_text_from_url(self, pdf_url: str) -> str:
        """
        Extract text from PDF URL
        
        Args:
            pdf_url: URL of the PDF
            
        Returns:
            Extracted text content
        """
        try:
            logger.info(f"Downloading PDF from: {pdf_url}")
            
            # Download PDF
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # Read PDF
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PdfReader(pdf_file)
            
            # Extract text from all pages
            text = ""
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    text += page_text + "\n\n"
                except Exception as e:
                    logger.warning(f"Error extracting page {page_num}: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(text)} characters from PDF")
            return text.strip()
            
        except requests.RequestException as e:
            logger.error(f"Error downloading PDF: {e}")
            raise Exception(f"Failed to download PDF: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise Exception(f"Failed to process PDF: {str(e)}")
    
    async def extract_text_from_file(self, file_path: str) -> str:
        """
        Extract text from local PDF file
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text content
        """
        try:
            logger.info(f"Reading PDF from: {file_path}")
            
            # Read PDF
            pdf_reader = PdfReader(file_path)
            
            # Extract text from all pages
            text = ""
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    text += page_text + "\n\n"
                except Exception as e:
                    logger.warning(f"Error extracting page {page_num}: {e}")
                    continue
            
            logger.info(f"Successfully extracted {len(text)} characters from PDF")
            return text.strip()
            
        except Exception as e:
            logger.error(f"Error processing PDF file: {e}")
            raise Exception(f"Failed to process PDF file: {str(e)}")
    
    def chunk_text(self, text: str) -> List[Dict[str, any]]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Full text content
            
        Returns:
            List of text chunks with metadata
        """
        chunks = []
        start = 0
        chunk_id = 0
        
        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size
            
            # Find a good breaking point (end of sentence)
            if end < len(text):
                # Look for period, newline, or other punctuation
                for i in range(end, max(start, end - 100), -1):
                    if text[i] in '.!?\n':
                        end = i + 1
                        break
            
            # Extract chunk
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunks.append({
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "start_pos": start,
                    "end_pos": end,
                    "length": len(chunk_text)
                })
                chunk_id += 1
            
            # Move start position (with overlap)
            start = end - self.chunk_overlap
        
        logger.info(f"Created {len(chunks)} chunks from text")
        return chunks
    
    async def process_pdf(self, pdf_source: str, is_url: bool = True) -> Dict:
        """
        Process PDF and return extracted text and chunks
        
        Args:
            pdf_source: URL or file path of PDF
            is_url: Whether source is URL (True) or file path (False)
            
        Returns:
            Dictionary with full text and chunks
        """
        try:
            # Extract text
            if is_url:
                full_text = await self.extract_text_from_url(pdf_source)
            else:
                full_text = await self.extract_text_from_file(pdf_source)
            
            # Create chunks
            chunks = self.chunk_text(full_text)
            
            return {
                "full_text": full_text,
                "chunks": chunks,
                "total_chunks": len(chunks),
                "total_chars": len(full_text),
                "source": pdf_source
            }
            
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise

# Global PDF handler instance
pdf_handler = PDFHandler()
