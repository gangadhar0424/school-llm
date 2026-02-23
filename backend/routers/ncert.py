from fastapi import APIRouter, HTTPException
from typing import Dict, List, Any
import sys
import os

# Add parent directory to path to import scraper
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scraper import NCERTScraper

router = APIRouter(prefix="/api/ncert", tags=["NCERT"])

# Cache for scraped data
_books_cache: Dict[str, Any] = {}

@router.get("/books")
async def get_all_books() -> Dict[str, Dict[str, List[Dict]]]:
    """
    Get all NCERT books for all classes (1-12)
    Returns: Dictionary with class-wise, subject-wise book data
    """
    global _books_cache
    
    # Return cached data if available
    if _books_cache:
        return _books_cache
    
    # Scrape fresh data
    try:
        scraper = NCERTScraper()
        books_data = scraper.scrape_books()
        _books_cache = books_data
        return books_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch NCERT books: {str(e)}")


@router.get("/books/class/{class_number}")
async def get_books_by_class(class_number: int) -> Dict[str, List[Dict]]:
    """
    Get books for a specific class (1-12)
    Args:
        class_number: Class number (1-12)
    Returns: Dictionary with subject-wise book data
    """
    if class_number < 1 or class_number > 12:
        raise HTTPException(status_code=400, detail="Class number must be between 1 and 12")
    
    books_data = await get_all_books()
    class_key = f"class_{class_number}"
    
    if class_key not in books_data:
        raise HTTPException(status_code=404, detail=f"No books found for class {class_number}")
    
    return books_data[class_key]


@router.get("/books/class/{class_number}/subject/{subject}")
async def get_books_by_subject(class_number: int, subject: str) -> List[Dict]:
    """
    Get books for a specific class and subject
    Args:
        class_number: Class number (1-12)
        subject: Subject name (e.g., mathematics, science, english)
    Returns: List of books for the subject
    """
    class_books = await get_books_by_class(class_number)
    
    if subject not in class_books:
        raise HTTPException(
            status_code=404, 
            detail=f"No books found for subject '{subject}' in class {class_number}"
        )
    
    return class_books[subject]


@router.post("/refresh")
async def refresh_books_cache() -> Dict[str, str]:
    """
    Force refresh the books cache by re-scraping
    Returns: Success message
    """
    global _books_cache
    
    try:
        scraper = NCERTScraper()
        books_data = scraper.scrape_books()
        _books_cache = books_data
        return {"message": "Books cache refreshed successfully", "total_classes": len(books_data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh cache: {str(e)}")
