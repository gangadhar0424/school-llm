"""
Sample Data Seeder for School LLM
Populates MongoDB with sample textbook data
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/school_llm")
DATABASE_NAME = "school_llm"

# Sample textbook data
SAMPLE_TEXTBOOKS = [
    # CBSE Class 9
    {
        "board": "CBSE",
        "class": "9",
        "subject": "Mathematics",
        "title": "NCERT Mathematics Class 9",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/iemh1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "9",
        "subject": "Science",
        "title": "NCERT Science Class 9",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/iesc1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "9",
        "subject": "English",
        "title": "NCERT Beehive Class 9",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/ieen1dd.pdf"
    },
    
    # CBSE Class 10
    {
        "board": "CBSE",
        "class": "10",
        "subject": "Mathematics",
        "title": "NCERT Mathematics Class 10",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/jemh1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "10",
        "subject": "Science",
        "title": "NCERT Science Class 10",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/jesc1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "10",
        "subject": "Social Science",
        "title": "NCERT Democratic Politics Class 10",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/jess4dd.pdf"
    },
    
    # CBSE Class 11
    {
        "board": "CBSE",
        "class": "11",
        "subject": "Physics",
        "title": "NCERT Physics Part 1 Class 11",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/keph1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "11",
        "subject": "Chemistry",
        "title": "NCERT Chemistry Part 1 Class 11",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/kech1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "11",
        "subject": "Mathematics",
        "title": "NCERT Mathematics Class 11",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/kemh1dd.pdf"
    },
    
    # CBSE Class 12
    {
        "board": "CBSE",
        "class": "12",
        "subject": "Physics",
        "title": "NCERT Physics Part 1 Class 12",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/leph1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "12",
        "subject": "Chemistry",
        "title": "NCERT Chemistry Part 1 Class 12",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/lech1dd.pdf"
    },
    {
        "board": "CBSE",
        "class": "12",
        "subject": "Mathematics",
        "title": "NCERT Mathematics Part 1 Class 12",
        "pdf_url": "https://ncert.nic.in/textbook/pdf/lemh1dd.pdf"
    },
    
    # ICSE
    {
        "board": "ICSE",
        "class": "10",
        "subject": "Mathematics",
        "title": "ICSE Mathematics Class 10",
        "pdf_url": "https://example.com/icse-math-10.pdf"
    },
    {
        "board": "ICSE",
        "class": "10",
        "subject": "Physics",
        "title": "ICSE Physics Class 10",
        "pdf_url": "https://example.com/icse-physics-10.pdf"
    },
    
    # State Boards
    {
        "board": "State Boards",
        "class": "10",
        "subject": "Mathematics",
        "title": "Maharashtra State Board Mathematics",
        "pdf_url": "https://example.com/mh-math-10.pdf"
    },
    
    # CAIE
    {
        "board": "CAIE",
        "class": "IGCSE",
        "subject": "Mathematics",
        "title": "Cambridge IGCSE Mathematics",
        "pdf_url": "https://example.com/cambridge-math.pdf"
    },
    
    # NIOS
    {
        "board": "NIOS",
        "class": "10",
        "subject": "Science",
        "title": "NIOS Science Class 10",
        "pdf_url": "https://example.com/nios-science-10.pdf"
    }
]

async def seed_database():
    """Populate database with sample textbook data"""
    print("🌱 Starting database seeding...")
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    
    try:
        # Clear existing data (optional - comment out if you want to keep existing data)
        print("📝 Clearing existing textbooks...")
        await db.textbooks.delete_many({})
        
        # Insert sample data
        print(f"📚 Inserting {len(SAMPLE_TEXTBOOKS)} sample textbooks...")
        result = await db.textbooks.insert_many(SAMPLE_TEXTBOOKS)
        
        print(f"✅ Successfully inserted {len(result.inserted_ids)} textbooks")
        
        # Display summary
        print("\n📊 Database Summary:")
        boards = await db.textbooks.distinct("board")
        print(f"   Boards: {', '.join(boards)}")
        
        for board in boards:
            count = await db.textbooks.count_documents({"board": board})
            print(f"   - {board}: {count} textbooks")
        
        print("\n✨ Database seeding completed successfully!")
        
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    print("=" * 60)
    print("School LLM - Database Seeder")
    print("=" * 60)
    print()
    
    asyncio.run(seed_database())
