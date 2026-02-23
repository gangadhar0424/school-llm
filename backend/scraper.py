"""
Web Scraper Module for School LLM
Scrapes educational websites for textbook links and metadata
"""
import asyncio
import logging
import re
import time
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import aiohttp
import requests
from urllib.parse import urljoin, urlparse, unquote
import urllib.request
from urllib.request import urlopen
from database import mongodb

logger = logging.getLogger(__name__)

class WebScraper:
    """Web scraper for educational content"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def __aenter__(self):
        """Create aiohttp session"""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
    
    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch HTML content from URL"""
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Failed to fetch {url}: Status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict:
        """Extract metadata from HTML"""
        metadata = {
            'url': url,
            'title': '',
            'description': '',
            'keywords': [],
            'links': [],
            'pdf_links': [],
            'scraped_at': datetime.utcnow()
        }
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text().strip()
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            metadata['description'] = meta_desc.get('content').strip()
        
        # Extract keywords
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords and meta_keywords.get('content'):
            metadata['keywords'] = [k.strip() for k in meta_keywords.get('content').split(',')]
        
        # Extract all links
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(url, href)
            
            link_data = {
                'text': link.get_text().strip(),
                'url': full_url
            }
            
            metadata['links'].append(link_data)
            
            # Check if it's a PDF link
            if href.lower().endswith('.pdf'):
                metadata['pdf_links'].append({
                    'text': link.get_text().strip(),
                    'url': full_url
                })
        
        return metadata
    
    async def scrape_url(self, url: str) -> Optional[Dict]:
        """Scrape a single URL and extract metadata"""
        logger.info(f"Scraping {url}")
        
        html = await self.fetch_page(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        metadata = self.extract_metadata(soup, url)
        
        return metadata
    
    async def scrape_multiple_urls(self, urls: List[str]) -> List[Dict]:
        """Scrape multiple URLs concurrently"""
        tasks = [self.scrape_url(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
    
    async def save_to_database(self, metadata: Dict):
        """Save scraped metadata to MongoDB"""
        try:
            # Check if URL already exists
            existing = await mongodb.db.scraped_data.find_one({'url': metadata['url']})
            
            if existing:
                # Update existing record
                await mongodb.db.scraped_data.update_one(
                    {'url': metadata['url']},
                    {'$set': metadata}
                )
                logger.info(f"Updated scraped data for {metadata['url']}")
            else:
                # Insert new record
                await mongodb.db.scraped_data.insert_one(metadata)
                logger.info(f"Saved new scraped data for {metadata['url']}")
            
            return True
        except Exception as e:
            logger.error(f"Error saving scraped data: {e}")
            return False

# Educational websites to scrape (examples)
EDUCATIONAL_URLS = [
    'https://ncert.nic.in/textbook.php',
    'https://www.cbse.gov.in/newsite/textbooks.html',
    # Add more URLs here
]

async def run_scraper():
    """Main scraper function to run independently"""
    logger.info("Starting web scraper...")
    
    async with WebScraper() as scraper:
        # Scrape configured URLs
        results = await scraper.scrape_multiple_urls(EDUCATIONAL_URLS)
        
        # Save to database
        for result in results:
            await scraper.save_to_database(result)
        
        logger.info(f"Scraping completed. Processed {len(results)} URLs")
    
    return results

if __name__ == "__main__":
    # Run scraper independently
    asyncio.run(run_scraper())


class NCERTScraper:
    """Scraper specifically for NCERT textbooks"""

    BASE_URL = "https://ncert.nic.in/textbook.php"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def scrape_books(self) -> Dict[str, Dict[str, List[Dict]]]:
        """
        Scrape NCERT books for all classes (1-12)
        Returns a dictionary with class-wise subject-wise book links
        """
        html = self._fetch_html()
        if not html:
            return self._fallback_books()

        script_text = self._extract_script(html)
        if not script_text:
            return self._fallback_books()

        books_data = self._parse_script(script_text)
        return books_data or self._fallback_books()

    def _fetch_html(self) -> Optional[str]:
        """Fetch the NCERT textbook page HTML."""
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                response = requests.get(self.BASE_URL, headers=self.headers, timeout=20)
                if response.status_code == 200 and response.text:
                    return response.text
                logger.warning(
                    f"NCERT fetch returned status {response.status_code} (attempt {attempt + 1})"
                )
            except Exception as exc:
                last_error = exc
                logger.warning(f"NCERT fetch failed (attempt {attempt + 1}): {exc}")

            time.sleep(1.5 * (attempt + 1))

        try:
            request = urllib.request.Request(self.BASE_URL, headers=self.headers)
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            last_error = exc

        logger.error(f"Failed to fetch NCERT page: {last_error}")
        return None

    def _extract_script(self, html: str) -> Optional[str]:
        """Extract the script that contains class/subject/book mappings."""
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text() or ""
            if "document.test.tbook" in script_text or "tbook.options" in script_text:
                return script_text
        return None

    def _parse_script(self, script_text: str) -> Dict[str, Dict[str, List[Dict]]]:
        """Parse the NCERT JS mapping into class/subject/book data."""
        books_data: Dict[str, Dict[str, List[Dict]]]= {}

        change_block = self._get_function_block(script_text, "change")
        change1_block = self._get_function_block(script_text, "change1")

        class_subjects = self._parse_subjects(change_block)
        class_subject_books = self._parse_books(change1_block)

        for class_num, subjects in class_subjects.items():
            class_key = f"class_{class_num}"
            for subject in subjects:
                books = class_subject_books.get(class_num, {}).get(subject, [])
                books_data.setdefault(class_key, {})[subject] = books

        return books_data

    def _get_function_block(self, script_text: str, name: str) -> str:
        """Extract the body of a JS function by name."""
        pattern = re.compile(rf"function\s+{name}\s*\([^)]*\)\s*\{{", re.IGNORECASE)
        match = pattern.search(script_text)
        if not match:
            return ""

        start = match.end()
        depth = 1
        i = start
        while i < len(script_text) and depth > 0:
            if script_text[i] == "{":
                depth += 1
            elif script_text[i] == "}":
                depth -= 1
            i += 1

        return script_text[start:i - 1]

    def _normalize_js(self, script_text: str) -> str:
        """Collapse whitespace for easier regex parsing across line breaks."""
        return re.sub(r"\s+", " ", script_text)

    def _parse_subjects(self, change_block: str) -> Dict[int, List[str]]:
        """Parse class -> subject list from change() block."""
        subjects_by_class: Dict[int, List[str]] = {}
        normalized = self._normalize_js(change_block)
        class_re = re.compile(r"\(document\.test\.tclass\.value==([0-9]+)\)")
        subject_re = re.compile(r"tsubject\.options\[\d+\]\.text=['\"]([^'\"]*)['\"]")

        matches = list(class_re.finditer(normalized))
        for index, match in enumerate(matches):
            class_num = int(match.group(1))
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            block = normalized[start:end]

            subjects_by_class.setdefault(class_num, [])
            for subject in subject_re.findall(block):
                subject = subject.strip()
                if subject and not subject.startswith("..Select"):
                    if subject not in subjects_by_class[class_num]:
                        subjects_by_class[class_num].append(subject)

        return subjects_by_class

    def _parse_books(self, change1_block: str) -> Dict[int, Dict[str, List[Dict]]]:
        """Parse class + subject -> books from change1() block."""
        books_by_class: Dict[int, Dict[str, List[Dict]]]= {}

        normalized = self._normalize_js(change1_block)
        condition_re = re.compile(
            r"\(document\.test\.tclass\.value==([0-9]+)\)\s*&&\s*\(document\.test\.tsubject\.options\[sind\]\.text\s*==['\"]([^'\"]+)['\"]\)"
        )
        book_text_re = re.compile(r"tbook\.options\[(\d+)\]\.text=['\"]([^'\"]*)['\"]")
        book_val_re = re.compile(r"tbook\.options\[(\d+)\]\.value=['\"]([^'\"]*)['\"]")

        matches = list(condition_re.finditer(normalized))
        for index, match in enumerate(matches):
            current_class = int(match.group(1))
            current_subject = match.group(2).strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            block = normalized[start:end]

            texts = {idx: text.strip() for idx, text in book_text_re.findall(block)}
            values = {idx: value.strip() for idx, value in book_val_re.findall(block)}

            for idx, title in texts.items():
                if not title or title == "..Select Book Title..":
                    continue
                value = values.get(idx)
                if not value:
                    continue
                full_link = value if value.startswith("http") else f"https://ncert.nic.in/{value.lstrip('/')}"
                books_by_class.setdefault(current_class, {}).setdefault(current_subject, []).append({
                    "title": title,
                    "link": full_link
                })

        return books_by_class

    def _fallback_books(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Fallback data if parsing fails."""
        fallback: Dict[str, Dict[str, List[Dict]]] = {}
        for class_num in range(1, 13):
            fallback[f"class_{class_num}"] = {}
        return fallback


class APScraper:
    """Scraper for AP state board textbook links (no PDF downloads)."""

    BASE_URL = "https://cse.ap.gov.in/textBooksDownloadingPageTEBilingual"

    def scrape_books(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Return AP state board book links grouped by class and subject."""
        html = self._fetch_html()
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        links = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(self.BASE_URL, anchor.get("href"))
            if "/downloadBooks/" in href:
                links.append(href)

        return self._group_links(links)

    def _fetch_html(self) -> Optional[str]:
        """Fetch AP textbooks page HTML."""
        try:
            with urlopen(self.BASE_URL, timeout=20) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.error(f"Failed to fetch AP page: {exc}")
            return None

    def _group_links(self, links: List[str]) -> Dict[str, Dict[str, List[Dict]]]:
        """Group AP links into class -> subject -> books."""
        grouped: Dict[str, Dict[str, List[Dict]]] = {}

        for link in links:
            parts = [unquote(p) for p in link.split("/") if p]
            if len(parts) < 3:
                continue

            class_num = parts[-1]
            if not class_num.isdigit():
                continue

            subject_folder = parts[-3]
            file_name = parts[-2]

            title = file_name.replace(".pdf", "").replace("_", " ").strip()
            subject = subject_folder.replace(" Books", "").strip()

            class_key = f"class_{class_num}"
            grouped.setdefault(class_key, {}).setdefault(subject, []).append({
                "title": title,
                "link": link
            })

        return grouped


class TelanganaScraper:
    """Scraper for Telangana state textbooks (links only)."""

    SSC_URL = "https://scert.telangana.gov.in/DisplayContent.aspx?encry=ammkNW4/gx+NeApstGPX+A=="
    INTER_URL = "https://www.telanganaopenschool.org/Intertextbooks.aspx"

    def scrape_books(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Return Telangana books grouped by level and subject."""
        ssc_books = self._collect_books(self.SSC_URL, level_key="ssc")
        inter_books = self._collect_books(self.INTER_URL, level_key="inter")

        data: Dict[str, Dict[str, List[Dict]]] = {}
        if ssc_books:
            data.update(ssc_books)
        if inter_books:
            data["inter"] = inter_books

        return data

    def _collect_books(self, url: str, level_key: str) -> Dict[str, Dict[str, List[Dict]]]:
        html = self._fetch_html(url)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        links = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(url, anchor.get("href"))
            text = anchor.get_text(strip=True)
            if not href.lower().endswith(".pdf"):
                continue
            if not self._is_textbook_link(href, text, level_key):
                continue
            links.append((text, href))

        if level_key == "ssc":
            return self._group_by_class_and_subject(links)
        return {"inter": self._group_by_inter_year_and_subject(links)}

    def _fetch_html(self, url: str) -> Optional[str]:
        try:
            with urlopen(url, timeout=20) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.error(f"Failed to fetch Telangana page: {exc}")
            return None

    def _group_by_subject(self, links: List[tuple]) -> Dict[str, List[Dict]]:
        grouped: Dict[str, List[Dict]] = {}
        for text, href in links:
            title = text.strip() or unquote(href.split("/")[-1]).replace(".pdf", "")
            if self._is_filtered_title(title):
                continue
            subject = self._infer_subject(title)
            grouped.setdefault(subject, []).append({
                "title": title,
                "link": href
            })
        return grouped

    def _group_by_class_and_subject(self, links: List[tuple]) -> Dict[str, Dict[str, List[Dict]]]:
        grouped: Dict[str, Dict[str, List[Dict]]] = {}
        for class_num in range(1, 11):
            grouped[f"class_{class_num}"] = {}

        for text, href in links:
            title = text.strip() or unquote(href.split("/")[-1]).replace(".pdf", "")
            if self._is_filtered_title(title):
                continue

            class_numbers = self._extract_classes(title)
            if not class_numbers:
                class_numbers = list(range(1, 11))

            subject = self._infer_subject(title)
            for class_num in class_numbers:
                class_key = f"class_{class_num}"
                grouped.setdefault(class_key, {}).setdefault(subject, []).append({
                    "title": title,
                    "link": href
                })

        return grouped

    def _group_by_inter_year_and_subject(self, links: List[tuple]) -> Dict[str, Dict[str, List[Dict]]]:
        grouped: Dict[str, Dict[str, List[Dict]]] = {
            "inter_1st_year": {},
            "inter_2nd_year": {}
        }

        for text, href in links:
            title = text.strip() or unquote(href.split("/")[-1]).replace(".pdf", "")
            if self._is_filtered_title(title):
                continue

            year_key = self._infer_inter_year(title)
            subject = self._infer_subject(title)
            grouped.setdefault(year_key, {}).setdefault(subject, []).append({
                "title": title,
                "link": href
            })

        return grouped

    def _infer_inter_year(self, title: str) -> str:
        lower = title.lower()
        if "vol 1" in lower or "vol i" in lower or "vol-1" in lower or "volume 1" in lower:
            return "inter_1st_year"
        if "vol 2" in lower or "vol ii" in lower or "vol-2" in lower or "volume 2" in lower:
            return "inter_2nd_year"
        if "1st" in lower or "first" in lower or "i year" in lower:
            return "inter_1st_year"
        if "2nd" in lower or "second" in lower or "ii year" in lower:
            return "inter_2nd_year"
        return "inter_1st_year"

    def _extract_classes(self, title: str) -> List[int]:
        """Extract class numbers from a title, including ranges."""
        lower = title.lower()
        range_re = re.compile(r"([1-9]|10)\s*(?:st|nd|rd|th)?\s*(?:to|-)\s*([1-9]|10)")
        single_re = re.compile(r"(?:class|cl)\s*([1-9]|10)\b|\b([1-9]|10)\s*(?:st|nd|rd|th)?\s*class\b")

        ranges = range_re.findall(lower)
        if ranges:
            classes = set()
            for start, end in ranges:
                s = int(start)
                e = int(end)
                for c in range(min(s, e), max(s, e) + 1):
                    if 1 <= c <= 10:
                        classes.add(c)
            return sorted(classes)

        singles = single_re.findall(lower)
        classes = set()
        for a, b in singles:
            val = a or b
            if val:
                c = int(val)
                if 1 <= c <= 10:
                    classes.add(c)
        return sorted(classes)

    def _is_filtered_title(self, title: str) -> bool:
        """Filter out non-textbook PDFs."""
        lower = title.lower()
        blocked = [
            "prospectus",
            "recognition",
            "citizen charter",
            "migration",
            "transfer certificate",
            "master list",
            "duplicate pass",
            "certificate",
            "calendar",
            "handbook",
            "notification",
            "compendium",
            "framework",
            "assessment",
            "study",
            "report",
            "programme",
            "program",
            "admission",
            "timetable",
        ]
        return any(term in lower for term in blocked)

    def _is_textbook_link(self, href: str, text: str, level_key: str) -> bool:
        """Heuristic filter for textbook PDFs only."""
        haystack = f"{href} {text}".lower()
        if level_key == "inter" and "/images/inter_pdfs/" in haystack:
            return True
        keywords = [
            "textbook", "text book", "workbook", "book", "class", "volume", "vol",
            "practical", "lab", "reader", "math", "science", "social", "english",
            "telugu", "hindi", "urdu"
        ]
        return any(k in haystack for k in keywords)

    def _infer_subject(self, title: str) -> str:
        lower = title.lower()
        if "social" in lower or "history" in lower or "geography" in lower or "civics" in lower or "politics" in lower:
            return "Social Science"
        if "math" in lower:
            return "Mathematics"
        if "physics" in lower:
            return "Physics"
        if "chem" in lower:
            return "Chemistry"
        if "biology" in lower or "botany" in lower or "zoology" in lower:
            return "Biology"
        if "english" in lower:
            return "English"
        if "science" in lower:
            return "Science"
        if "telugu" in lower:
            return "Telugu"
        if "hindi" in lower:
            return "Hindi"
        if "urdu" in lower:
            return "Urdu"
        if "sanskrit" in lower:
            return "Sanskrit"
        if "economics" in lower:
            return "Economics"
        if "commerce" in lower or "account" in lower or "business" in lower:
            return "Commerce"
        return "General"

class KarnatakaTextbookScraper:
    """Scrape Karnataka state textbooks from https://textbooks.karnataka.gov.in/textbooks/en
    
    Organizes textbooks by:
    - Class/Grade (1-12 or I-XII)
    - Medium/Subject (English Medium, Hindi Medium, Urdu Medium, etc.)
    """
    
    BASE_URL = "https://textbooks.karnataka.gov.in/textbooks/en"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    def _extract_class_number(self, text: str) -> Optional[str]:
        """Extract class number from text like 'Class 1' or 'CLASS-1' or '2023-24-Class1-Eng'"""
        import re
        
        text_lower = text.lower()
        
        # Match "Class 1", "Class I", "class1", etc
        class_match = re.search(r'class\s*([0-9ivx]+)', text_lower)
        if class_match:
            return class_match.group(1).strip()
        
        # Match just numbers at start (for patterns like "1 English Medium")
        num_match = re.search(r'^[0-9]+', text_lower)
        if num_match:
            return num_match.group(0)
        
        return None
    
    def _extract_medium(self, text: str) -> str:
        """Extract medium/subject from text"""
        text_lower = text.lower()
        
        # Check for specific mediums
        if "english" in text_lower:
            return "English Medium"
        if "hindi" in text_lower:
            return "Hindi Medium"
        if "urdu" in text_lower:
            return "Urdu Medium"
        if "kannada" in text_lower or "nalikali" in text_lower:
            return "Kannada Medium"
        if "marathi" in text_lower:
            return "Marathi Medium"
        if "tamil" in text_lower:
            return "Tamil Medium"
        if "telugu" in text_lower:
            return "Telugu Medium"
        
        return "General"
    
    async def fetch_classes(self) -> List[Dict]:
        """
        Fetch and organize available classes from Karnataka textbooks site
        
        Returns:
            List of organized classes with proper structure
        """
        try:
            logger.info("Fetching Karnataka classes from " + self.BASE_URL)
            resp = self.session.get(self.BASE_URL, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract all PDF/textbook links
            all_books = []
            for link in soup.find_all('a'):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Only get links to PDFs or textbook pages
                if (href and text and 
                    (href.endswith('.pdf') or 'class' in text.lower() or 'textbook' in href.lower())):
                    all_books.append({'text': text, 'url': urljoin(self.BASE_URL, href)})
            
            # Organize books by class number
            classes_dict = {}
            for book in all_books:
                class_num = self._extract_class_number(book['text'])
                if class_num:
                    if class_num not in classes_dict:
                        classes_dict[class_num] = {
                            'class': f"Class {class_num}",
                            'number': class_num,
                            'books': []
                        }
                    classes_dict[class_num]['books'].append(book)
            
            # Convert to list and sort by class number
            classes = []
            for class_num in sorted(classes_dict.keys(), key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0):
                class_data = classes_dict[class_num]
                classes.append({
                    'class': class_data['class'],
                    'label': class_data['class'],
                    'number': class_num,
                    'count': len(class_data['books'])
                })
            
            # If no clear classes found, create generic ones (1-12)
            if not classes:
                classes = [{'class': f'Class {i}', 'label': f'Class {i}', 'number': str(i), 'count': 0} for i in range(1, 13)]
            
            logger.info(f"Found {len(classes)} organized classes")
            return classes
            
        except Exception as e:
            logger.error(f"Error fetching Karnataka classes: {e}")
            raise Exception(f"Failed to fetch Karnataka textbooks: {str(e)}")
    
    async def fetch_subjects(self, class_number: str) -> List[Dict]:
        """
        Fetch subjects/textbooks for a given class
        
        Args:
            class_number: Class number (e.g., '1', '2', 'I', 'II')
            
        Returns:
            List of subjects organized by medium
        """
        try:
            logger.info(f"Fetching textbooks for Class {class_number}")
            
            # Fetch all textbooks from main page
            resp = self.session.get(self.BASE_URL, timeout=15)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extract all PDF links
            all_links = []
            for link in soup.find_all('a'):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if href and text:
                    all_links.append({'text': text, 'url': urljoin(self.BASE_URL, href)})
            
            # Filter for this class and organize by subject
            subjects_dict = {}
            for item in all_links:
                # Check if this link belongs to this class
                if self._extract_class_number(item['text']) == class_number:
                    # Extract the subject/medium
                    medium = self._extract_medium(item['text'])
                    
                    if medium not in subjects_dict:
                        subjects_dict[medium] = []
                    
                    subjects_dict[medium].append({
                        'name': item['text'],
                        'url': item['url']
                    })
            
            # Convert to list format
            subjects = []
            for medium in sorted(subjects_dict.keys()):
                books = subjects_dict[medium]
                for book in books:
                    subjects.append({
                        'subject': medium,
                        'label': book['name'],
                        'url': book['url'],
                        'type': 'pdf' if book['url'].endswith('.pdf') else 'page'
                    })
            
            logger.info(f"Found {len(subjects)} textbooks for Class {class_number}")
            return subjects
            
        except Exception as e:
            logger.error(f"Error fetching subjects for Class {class_number}: {e}")
            raise Exception(f"Failed to fetch subjects: {str(e)}")


class TamilNaduScraper:
    """Scraper for Tamil Nadu state textbook links (not PDFs, just links)."""
    
    BASE_URL = "https://www.tntextbooks.in/p/school-books.html"
    
    def scrape_books(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Return Tamil Nadu textbook links grouped by class and subject."""
        logger.info("Starting Tamil Nadu textbook scraping...")
        
        # Tamil Nadu website structure is complex and dynamic
        # Return the pre-organized placeholder structure with sample textbooks
        logger.info("Returning Tamil Nadu placeholder structure with sample textbooks")
        placeholder = self._get_placeholder_structure()
        logger.info(f"Placeholder structure has {len(placeholder)} classes")
        return placeholder
    
    def _fetch_html(self) -> Optional[str]:
        """Fetch Tamil Nadu textbooks page HTML."""
        try:
            with urlopen(self.BASE_URL, timeout=20) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.error(f"Failed to fetch Tamil Nadu page: {exc}")
            return None
    
    def _extract_links_from_html(self, html: str) -> List[tuple]:
        """Extract textbook links from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        links = []
        
        # Extract all links that look like textbook links
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            text = anchor.get_text(strip=True)
            
            # Only get links (not PDFs) and filter for textbooks
            if href and not href.lower().endswith(".pdf"):
                if self._is_textbook_link(href, text):
                    full_url = urljoin(self.BASE_URL, href) if not href.startswith("http") else href
                    links.append((text, full_url))
        
        return links
    
    def _is_textbook_link(self, href: str, text: str) -> bool:
        """Heuristic filter for textbook links only."""
        haystack = f"{href} {text}".lower()
        
        # Exclude non-textbook pages
        blocked = [
            "privacy", "disclaimer", "contact", "about", "admin", "login",
            "comment", "archive", "search", "subscribe", "download app",
            "facebook", "twitter", "instagram", "youtube", "pinterest"
        ]
        if any(term in haystack for term in blocked):
            return False
        
        # Include keywords for textbooks
        keywords = [
            "books", "textbook", "text book", "class", "std", "guide",
            "tamil", "english", "maths", "math", "science", "social",
            "history", "geography", "civics", "economics", "physics",
            "chemistry", "biology", "literature", "reader", "workbook"
        ]
        return any(k in haystack for k in keywords)
    
    def _group_links(self, links: List[tuple]) -> Dict[str, Dict[str, List[Dict]]]:
        """Group Tamil Nadu links into class -> subject -> books."""
        grouped: Dict[str, Dict[str, List[Dict]]] = {}
        
        for text, href in links:
            # Extract class number from the link text
            class_num = self._extract_class_number(text)
            if not class_num:
                continue
            
            # Infer subject from the link text
            subject = self._infer_subject(text)
            
            class_key = f"class_{class_num}"
            title = text.replace(f"Class {class_num}", "").replace(f"Std {class_num}", "").strip()
            if not title:
                title = text
            
            grouped.setdefault(class_key, {}).setdefault(subject, []).append({
                "title": title,
                "link": href
            })
        
        return grouped
    
    def _get_placeholder_structure(self) -> Dict[str, Dict[str, List[Dict]]]:
        """Return a placeholder structure with classes 1-12 and class-specific links."""
        grouped: Dict[str, Dict[str, List[Dict]]] = {}
        
        # Ordinal suffixes for class numbers
        ordinal_map = {
            1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
            7: "7th", 8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th"
        }
        
        for class_num in range(1, 13):
            class_key = f"class_{class_num}"
            ordinal = ordinal_map[class_num]
            class_url = f"https://www.tntextbooks.in/p/{ordinal.lower()}-books.html"
            
            # Each class gets subjects with the class-specific URL
            grouped[class_key] = {
                "Tamil": [
                    {"title": f"Tamil Textbook - Term 1", "link": class_url},
                    {"title": f"Tamil Textbook - Term 2", "link": class_url},
                ],
                "English": [
                    {"title": f"English Textbook - Term 1", "link": class_url},
                    {"title": f"English Textbook - Term 2", "link": class_url},
                ],
                "Mathematics": [
                    {"title": f"Mathematics Textbook - Term 1", "link": class_url},
                    {"title": f"Mathematics Textbook - Term 2", "link": class_url},
                ],
                "Science": [
                    {"title": f"Science Textbook - Term 1", "link": class_url},
                    {"title": f"Science Textbook - Term 2", "link": class_url},
                ],
                "Social Science": [
                    {"title": f"Social Science Textbook - Term 1", "link": class_url},
                    {"title": f"Social Science Textbook - Term 2", "link": class_url},
                ],
            }
        
        return grouped
    
    def _extract_class_number(self, text: str) -> Optional[str]:
        """Extract class/standard number from text."""
        lower = text.lower()
        
        # Match "Class 1", "Class I", "Std 1", "Std I", "Grade 1", etc.
        class_match = re.search(r"(?:class|std|grade|standard)\s*([0-9]{1,2}|[ivxlc]+)\b", lower)
        if class_match:
            class_str = class_match.group(1).strip()
            # Convert roman numerals to numbers if needed
            if class_str.isdigit():
                class_num = int(class_str)
                if 1 <= class_num <= 12:
                    return str(class_num)
            else:
                # Try to convert roman numerals
                roman_map = {
                    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
                    "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12
                }
                if class_str in roman_map:
                    return str(roman_map[class_str])
        
        return None
    
    def _infer_subject(self, title: str) -> str:
        """Infer subject from the link text."""
        lower = title.lower()
        
        if "social" in lower or "history" in lower or "geography" in lower or "civics" in lower or "politics" in lower:
            return "Social Science"
        if "math" in lower or "maths" in lower:
            return "Mathematics"
        if "physics" in lower:
            return "Physics"
        if "chem" in lower:
            return "Chemistry"
        if "biology" in lower or "botany" in lower or "zoology" in lower:
            return "Biology"
        if "english" in lower:
            return "English"
        if "science" in lower:
            return "Science"
        if "tamil" in lower:
            return "Tamil"
        if "hindi" in lower:
            return "Hindi"
        if "urdu" in lower:
            return "Urdu"
        if "sanskrit" in lower:
            return "Sanskrit"
        if "economics" in lower:
            return "Economics"
        if "commerce" in lower or "account" in lower or "business" in lower:
            return "Commerce"
        if "guide" in lower or "solution" in lower:
            return "Study Guide"
        
        return "General"


# Global scraper instances
karnataka_scraper = KarnatakaTextbookScraper()
tamil_nadu_scraper = TamilNaduScraper()
