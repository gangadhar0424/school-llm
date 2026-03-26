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
from config import settings

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

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

    def _extract_pages_from_reader(self, pdf_reader: PdfReader) -> List[str]:
        """Extract text page-by-page from PdfReader."""
        pages_text: List[str] = []
        for page_num, page in enumerate(pdf_reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
                pages_text.append(page_text.strip())
            except Exception as e:
                logger.warning(f"Error extracting page {page_num}: {e}")
                pages_text.append("")
        return pages_text

    def _extract_pages_with_pymupdf_bytes(self, pdf_bytes: bytes) -> List[str]:
        """Fast page-by-page extraction from PDF bytes using PyMuPDF."""
        if fitz is None:
            raise RuntimeError("PyMuPDF is not available")

        pages_text: List[str] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_num, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text") or ""
                    pages_text.append(page_text.strip())
                except Exception as e:
                    logger.warning(f"PyMuPDF error extracting page {page_num}: {e}")
                    pages_text.append("")
        finally:
            doc.close()

        return pages_text

    def _extract_pages_with_pymupdf_file(self, file_path: str) -> List[str]:
        """Fast page-by-page extraction from local PDF file using PyMuPDF."""
        if fitz is None:
            raise RuntimeError("PyMuPDF is not available")

        pages_text: List[str] = []
        doc = fitz.open(file_path)
        try:
            for page_num, page in enumerate(doc, start=1):
                try:
                    page_text = page.get_text("text") or ""
                    pages_text.append(page_text.strip())
                except Exception as e:
                    logger.warning(f"PyMuPDF error extracting page {page_num}: {e}")
                    pages_text.append("")
        finally:
            doc.close()

        return pages_text

    def _join_pages_text(self, pages_text: List[str]) -> str:
        return "\n\n".join([p for p in pages_text if p]).strip()
    
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
            
            # Headers to mimic browser request (some servers reject Python requests)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/pdf,*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Download PDF with allow_redirects to follow redirects to actual PDF
            response = requests.get(pdf_url, timeout=30, allow_redirects=True, headers=headers)
            response.raise_for_status()

            # Validate response is actually a PDF
            content_type = response.headers.get("content-type", "").lower()
            if "application/pdf" not in content_type:
                logger.error(f"Invalid content type: {content_type}. URL does not point to a PDF file.")
                raise Exception(f"URL does not return a PDF. Content-Type: {content_type}. Please provide a direct link to a PDF file (not a webpage).")

            # Fast path: PyMuPDF is much faster on large PDFs.
            if fitz is not None:
                pages_text = self._extract_pages_with_pymupdf_bytes(response.content)
            else:
                pdf_file = io.BytesIO(response.content)
                pdf_reader = PdfReader(pdf_file)
                pages_text = self._extract_pages_from_reader(pdf_reader)

            text = self._join_pages_text(pages_text)
            
            logger.info(f"Successfully extracted {len(text)} characters from PDF")
            return text.strip()
            
        except requests.ConnectionError as e:
            logger.error(f"Connection error downloading PDF: {e}")
            raise Exception(f"Connection failed. The server may have rejected or closed the connection. Try a different PDF URL or check your internet connection.")
        except requests.RequestException as e:
            logger.error(f"Error downloading PDF: {e}")
            raise Exception(f"Failed to download PDF from URL. Check the link is accessible: {str(e)}")
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
            
            # Fast path: PyMuPDF is much faster on large PDFs.
            if fitz is not None:
                pages_text = self._extract_pages_with_pymupdf_file(file_path)
            else:
                pdf_reader = PdfReader(file_path)
                pages_text = self._extract_pages_from_reader(pdf_reader)

            text = self._join_pages_text(pages_text)
            
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
        if not text:
            return []

        chunks = []
        start = 0
        chunk_id = 0
        text_len = len(text)
        
        while start < text_len:
            # Calculate end position
            end = start + self.chunk_size
            
            # Find a good breaking point (end of sentence)
            if end < text_len:
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
            next_start = end - self.chunk_overlap
            start = next_start if next_start > start else end
        
        logger.info(f"Created {len(chunks)} chunks from text")
        return chunks

    def chunk_pages_text(self, pages_text: List[str]) -> List[Dict[str, any]]:
        """Split each page into overlapping chunks while preserving page metadata."""
        chunks: List[Dict[str, any]] = []
        chunk_id = 0

        for page_number, page_text in enumerate(pages_text, start=1):
            if not page_text:
                continue

            start = 0
            page_len = len(page_text)

            while start < page_len:
                end = start + self.chunk_size
                if end < page_len:
                    for i in range(end, max(start, end - 100), -1):
                        if page_text[i] in '.!?\n':
                            end = i + 1
                            break

                chunk_body = page_text[start:end].strip()
                if chunk_body:
                    chunks.append({
                        "chunk_id": chunk_id,
                        "text": chunk_body,
                        "page_number": page_number,
                        "start_pos": start,
                        "end_pos": end,
                        "length": len(chunk_body)
                    })
                    chunk_id += 1

                next_start = end - self.chunk_overlap
                start = next_start if next_start > start else end

        logger.info(f"Created {len(chunks)} page-aware chunks from {len(pages_text)} pages")
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
                # Headers to mimic browser request (some servers reject Python requests)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/pdf,*/*',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                response = requests.get(pdf_source, timeout=30, allow_redirects=True, headers=headers)
                response.raise_for_status()

                # Validate response is actually a PDF
                content_type = response.headers.get("content-type", "").lower()
                if "application/pdf" not in content_type:
                    logger.error(f"Invalid content type: {content_type}. URL does not point to a PDF file.")
                    raise Exception(f"URL does not return a PDF. Content-Type: {content_type}. Please provide a direct link to a PDF file (not a webpage).")

                if fitz is not None:
                    pages_text = self._extract_pages_with_pymupdf_bytes(response.content)
                else:
                    pdf_file = io.BytesIO(response.content)
                    pdf_reader = PdfReader(pdf_file)
                    pages_text = self._extract_pages_from_reader(pdf_reader)
            else:
                if fitz is not None:
                    pages_text = self._extract_pages_with_pymupdf_file(pdf_source)
                else:
                    pdf_reader = PdfReader(pdf_source)
                    pages_text = self._extract_pages_from_reader(pdf_reader)

            full_text = self._join_pages_text(pages_text)
            
            # Create page-aware chunks (enables citations).
            chunks = self.chunk_pages_text(pages_text)
            
            return {
                "full_text": full_text,
                "pages_text": pages_text,
                "total_pages": len(pages_text),
                "chunks": chunks,
                "total_chunks": len(chunks),
                "total_chars": len(full_text),
                "source": pdf_source
            }
            
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise

# Global PDF handler instance
pdf_handler = PDFHandler(
    chunk_size=settings.CHUNK_SIZE,
    chunk_overlap=settings.CHUNK_OVERLAP
)
