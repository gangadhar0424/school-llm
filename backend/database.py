"""
MongoDB database connection and models for School LLM
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from typing import Optional, List, Dict, ClassVar, Any
from datetime import datetime
from config import settings
import logging

logger = logging.getLogger(__name__)

class MongoDB:
    """MongoDB connection manager"""
    
    client: ClassVar[Optional[AsyncIOMotorClient]] = None
    db: ClassVar[Optional[Any]] = None
    
    @classmethod
    async def connect(cls):
        """Connect to MongoDB"""
        try:
            cls.client = AsyncIOMotorClient(settings.MONGODB_URI)
            cls.db = cls.client[settings.DATABASE_NAME]
            
            # Test connection
            await cls.client.admin.command('ping')
            logger.info("✅ Connected to MongoDB successfully")
            
            # Create indexes
            await cls.create_indexes()
            
        except ConnectionFailure as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
    @classmethod
    async def disconnect(cls):
        """Disconnect from MongoDB"""
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed")
    
    @classmethod
    async def create_indexes(cls):
        """Create database indexes for better query performance"""
        try:
            # Textbooks collection indexes
            await cls.db.textbooks.create_index([("board", 1), ("class", 1), ("subject", 1)])
            await cls.db.textbooks.create_index("title")
            
            logger.info("Database indexes created")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

# Database instance
mongodb = MongoDB()

# Collection interfaces
class TextbookDB:
    """Interface for textbooks collection"""
    
    @staticmethod
    async def get_all_boards() -> List[str]:
        """Get all unique boards"""
        boards = await mongodb.db.textbooks.distinct("board")
        return boards
    
    @staticmethod
    async def get_classes_by_board(board: str) -> List[str]:
        """Get all classes for a specific board"""
        classes = await mongodb.db.textbooks.distinct("class", {"board": board})
        return sorted(classes)
    
    @staticmethod
    async def get_subjects_by_board_and_class(board: str, class_name: str) -> List[str]:
        """Get all subjects for a specific board and class"""
        subjects = await mongodb.db.textbooks.distinct(
            "subject", 
            {"board": board, "class": class_name}
        )
        return sorted(subjects)
    
    @staticmethod
    async def get_textbooks(board: str = None, class_name: str = None, subject: str = None) -> List[Dict]:
        """Get textbooks with optional filters"""
        query = {}
        if board:
            query["board"] = board
        if class_name:
            query["class"] = class_name
        if subject:
            query["subject"] = subject
        
        cursor = mongodb.db.textbooks.find(query)
        textbooks = await cursor.to_list(length=None)
        
        # Convert ObjectId to string
        for book in textbooks:
            book["_id"] = str(book["_id"])
        
        return textbooks
    
    @staticmethod
    async def get_textbook_by_id(textbook_id: str) -> Optional[Dict]:
        """Get a specific textbook by ID"""
        from bson import ObjectId
        
        try:
            textbook = await mongodb.db.textbooks.find_one({"_id": ObjectId(textbook_id)})
            if textbook:
                textbook["_id"] = str(textbook["_id"])
            return textbook
        except:
            return None
    
    @staticmethod
    async def create_textbook(textbook_data: Dict) -> str:
        """Create a new textbook entry"""
        textbook_data["created_at"] = datetime.utcnow()
        result = await mongodb.db.textbooks.insert_one(textbook_data)
        return str(result.inserted_id)
    
    @staticmethod
    async def search_textbooks(query: str) -> List[Dict]:
        """Search textbooks by title or subject"""
        cursor = mongodb.db.textbooks.find({
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"subject": {"$regex": query, "$options": "i"}},
                {"board": {"$regex": query, "$options": "i"}}
            ]
        })
        
        textbooks = await cursor.to_list(length=50)
        
        for book in textbooks:
            book["_id"] = str(book["_id"])
        
        return textbooks

class SessionDB:
    """Interface for user sessions (stores current PDF context)"""
    
    @staticmethod
    async def create_session(session_data: Dict) -> str:
        """Create a new session"""
        session_data["created_at"] = datetime.utcnow()
        result = await mongodb.db.sessions.insert_one(session_data)
        return str(result.inserted_id)
    
    @staticmethod
    async def get_session(session_id: str) -> Optional[Dict]:
        """Get session by ID"""
        from bson import ObjectId
        
        try:
            session = await mongodb.db.sessions.find_one({"_id": ObjectId(session_id)})
            if session:
                session["_id"] = str(session["_id"])
            return session
        except:
            return None
    
    @staticmethod
    async def update_session(session_id: str, update_data: Dict):
        """Update session data"""
        from bson import ObjectId
        
        try:
            await mongodb.db.sessions.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": update_data}
            )
        except Exception as e:
            logger.error(f"Error updating session: {e}")

class UserDB:
    """User database operations"""
    
    @staticmethod
    async def create_user(user_data: Dict) -> Optional[str]:
        """Create a new user"""
        try:
            result = await mongodb.db.users.insert_one(user_data)
            logger.info(f"Created user: {user_data['email']}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            return None
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[Dict]:
        """Get user by email"""
        try:
            user = await mongodb.db.users.find_one({'email': email})
            if user:
                user['id'] = str(user['_id'])
            return user
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        try:
            from bson import ObjectId
            user = await mongodb.db.users.find_one({'_id': ObjectId(user_id)})
            if user:
                user['id'] = str(user['_id'])
            return user
        except Exception as e:
            logger.error(f"Failed to get user: {e}")
            return None
    
    @staticmethod
    async def update_user(email: str, update_data: Dict) -> bool:
        """Update user information"""
        try:
            result = await mongodb.db.users.update_one(
                {'email': email},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return False

class ScraperDB:
    """Scraped data database operations"""
    
    @staticmethod
    async def save_scraped_data(data: Dict) -> Optional[str]:
        """Save scraped website data"""
        try:
            # Check if URL already exists
            existing = await mongodb.db.scraped_data.find_one({'url': data['url']})
            
            if existing:
                # Update existing
                await mongodb.db.scraped_data.update_one(
                    {'url': data['url']},
                    {'$set': data}
                )
                return str(existing['_id'])
            else:
                # Insert new
                result = await mongodb.db.scraped_data.insert_one(data)
                return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to save scraped data: {e}")
            return None
    
    @staticmethod
    async def get_all_scraped_data() -> List[Dict]:
        """Get all scraped data"""
        try:
            cursor = mongodb.db.scraped_data.find()
            data = await cursor.to_list(length=None)
            for item in data:
                item['id'] = str(item['_id'])
            return data
        except Exception as e:
            logger.error(f"Failed to get scraped data: {e}")
            return []
    
    @staticmethod
    async def get_scraped_pdfs() -> List[Dict]:
        """Get all scraped PDF links"""
        try:
            cursor = mongodb.db.scraped_data.find({'pdf_links': {'$exists': True, '$ne': []}})
            data = await cursor.to_list(length=None)
            
            # Flatten PDF links
            all_pdfs = []
            for item in data:
                for pdf in item.get('pdf_links', []):
                    all_pdfs.append({
                        'source_url': item['url'],
                        'pdf_url': pdf['url'],
                        'pdf_text': pdf['text'],
                        'scraped_at': item['scraped_at']
                    })
            
            return all_pdfs
        except Exception as e:
            logger.error(f"Failed to get scraped PDFs: {e}")
            return []
    
    @staticmethod
    async def update_scraped_data(data_id: str, update_data: Dict) -> bool:
        """Update scraped data entry"""
        try:
            from bson import ObjectId
            result = await mongodb.db.scraped_data.update_one(
                {'_id': ObjectId(data_id)},
                {'$set': update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update scraped data: {e}")
            return False
    
    @staticmethod
    async def delete_scraped_data(data_id: str) -> bool:
        """Delete scraped data entry"""
        try:
            from bson import ObjectId
            result = await mongodb.db.scraped_data.delete_one({'_id': ObjectId(data_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete scraped data: {e}")
            return False

class UserActivityDB:
    """User activity tracking database operations"""
    
    @staticmethod
    async def log_activity(user_email: str, activity_type: str, details: Dict = None):
        """Log user activity"""
        try:
            activity = {
                'user_email': user_email,
                'activity_type': activity_type,  # login, page_view, resource_access, etc.
                'details': details or {},
                'timestamp': datetime.utcnow()
            }
            await mongodb.db.user_activity.insert_one(activity)
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
    
    @staticmethod
    async def get_user_activity(user_email: str = None, limit: int = 100) -> List[Dict]:
        """Get user activity logs"""
        try:
            query = {'user_email': user_email} if user_email else {}
            cursor = mongodb.db.user_activity.find(query).sort('timestamp', -1).limit(limit)
            activities = await cursor.to_list(length=None)
            
            for activity in activities:
                activity['id'] = str(activity['_id'])
                del activity['_id']
            
            return activities
        except Exception as e:
            logger.error(f"Failed to get user activity: {e}")
            return []
    
    @staticmethod
    async def get_all_users_with_activity() -> List[Dict]:
        """Get all users with their last activity"""
        try:
            # Get all users
            users_cursor = mongodb.db.users.find()
            users = await users_cursor.to_list(length=None)
            
            result = []
            for user in users:
                # Get last activity for this user
                last_activity = await mongodb.db.user_activity.find_one(
                    {'user_email': user['email']},
                    sort=[('timestamp', -1)]
                )
                
                # Get login count
                login_count = await mongodb.db.user_activity.count_documents({
                    'user_email': user['email'],
                    'activity_type': 'login'
                })
                
                result.append({
                    'id': str(user['_id']),
                    'email': user['email'],
                    'username': user['username'],
                    'full_name': user.get('full_name', ''),
                    'is_admin': user.get('is_admin', False),
                    'is_active': user.get('is_active', True),
                    'created_at': user['created_at'].isoformat(),
                    'last_login': last_activity['timestamp'].isoformat() if last_activity else None,
                    'login_count': login_count
                })
            
            return result
        except Exception as e:
            logger.error(f"Failed to get users with activity: {e}")
            return []

# Create singleton instances
mongodb = MongoDB()
textbook_db = TextbookDB()
session_db = SessionDB()
user_db = UserDB()
scraper_db = ScraperDB()
activity_db = UserActivityDB()
