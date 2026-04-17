import asyncio
import os
import sys
sys.path.append(os.path.abspath("backend"))

from backend.pdf_handler import PDFHandler
from backend.ai.qa import QASystem

async def check():
    handler = PDFHandler()
    qa_sys = QASystem()
    uploads_dir = r"c:\Users\ganga\OneDrive\Desktop\school-llm\runtime_data\uploads"
    for f in os.listdir(uploads_dir):
        if not f.endswith(".pdf"): continue
        full_path = os.path.join(uploads_dir, f)
        print(f"--- {f} ---")
        try:
            data = await handler.process_pdf(full_path, is_url=False)
            pages = data.get("pages_text", [])
            full_text = "\n".join(pages)
            chapters = qa_sys._extract_chapter_lines(full_text)
            topics = qa_sys._extract_topic_lines(full_text)
            print("Chapters:", chapters[:5])
            print("Topics:", topics[:5])
            if any("Inland seas" in c for c in chapters) or any("Inland seas" in t for t in topics):
                print("FOUND INLAND SEAS!")
        except Exception as e:
            print(f"Error processing {f}: {e}")

if __name__ == "__main__":
    asyncio.run(check())
