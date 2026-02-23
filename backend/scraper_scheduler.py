"""
Independent Web Scraper Scheduler
Runs the web scraper at regular intervals and saves data to MongoDB
This script runs independently of the backend server
"""
import asyncio
import schedule
import time
import logging
from datetime import datetime
from scraper import run_scraper
from database import mongodb

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def scheduled_scrape():
    """Run scraper and log results"""
    try:
        logger.info("=" * 60)
        logger.info(f"Starting scheduled scrape at {datetime.now()}")
        logger.info("=" * 60)
        
        # Connect to MongoDB
        await mongodb.connect()
        
        # Run scraper
        results = await run_scraper()
        
        logger.info(f"Scraping completed successfully")
        logger.info(f"URLs scraped: {len(results)}")
        logger.info(f"Timestamp: {datetime.now()}")
        logger.info("=" * 60)
        
        # Disconnect from MongoDB
        await mongodb.disconnect()
        
    except Exception as e:
        logger.error(f"Error during scheduled scrape: {e}", exc_info=True)

def run_async_scrape():
    """Wrapper to run async function in sync context"""
    asyncio.run(scheduled_scrape())

def main():
    """Main scheduler function"""
    logger.info("🚀 Starting School LLM Web Scraper Scheduler")
    logger.info("=" * 60)
    logger.info("Schedule Configuration:")
    logger.info("  - Runs every 6 hours")
    logger.info("  - Logs saved to: scraper_scheduler.log")
    logger.info("  - Database: MongoDB")
    logger.info("=" * 60)
    
    # Schedule scraper to run every 6 hours
    schedule.every(6).hours.do(run_async_scrape)
    
    # Also run immediately on startup
    logger.info("Running initial scrape...")
    run_async_scrape()
    
    # Keep running
    logger.info("\n✅ Scheduler is running. Press Ctrl+C to stop.\n")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\n🛑 Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in scheduler: {e}", exc_info=True)
