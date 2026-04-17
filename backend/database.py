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
            logger.info("Database indexes created")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

# Database instance
mongodb = MongoDB()

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

class PDFUploadDB:
    """PDF upload tracking database operations"""
    
    @staticmethod
    async def log_upload(
        filename: str,
        file_size: int,
        uploader_email: str = None,
        pdf_identifier: str = None,
        stored_filename: str = None
    ) -> str:
        """Log a PDF upload"""
        try:
            pdf_record = {
                'filename': filename,
                'file_size': file_size,
                'uploader_email': uploader_email,
                'upload_date': datetime.utcnow(),
                'pdf_identifier': pdf_identifier or f"upload_{filename}",
                'stored_filename': stored_filename
            }
            result = await mongodb.db.uploaded_pdfs.insert_one(pdf_record)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to log PDF upload: {e}")
            return None
    
    @staticmethod
    async def get_all_uploads(limit: int = 100) -> List[Dict]:
        """Get all uploaded PDFs"""
        try:
            cursor = mongodb.db.uploaded_pdfs.find().sort('upload_date', -1).limit(limit)
            uploads = await cursor.to_list(length=None)
            
            for upload in uploads:
                upload['id'] = str(upload['_id'])
                del upload['_id']
            
            return uploads
        except Exception as e:
            logger.error(f"Failed to get uploaded PDFs: {e}")
            return []
    
    @staticmethod
    async def get_user_uploads(user_email: str, limit: int = 50) -> List[Dict]:
        """Get uploads by a specific user"""
        try:
            cursor = mongodb.db.uploaded_pdfs.find(
                {'uploader_email': user_email}
            ).sort('upload_date', -1).limit(limit)
            uploads = await cursor.to_list(length=None)
            
            for upload in uploads:
                upload['id'] = str(upload['_id'])
                del upload['_id']
            
            return uploads
        except Exception as e:
            logger.error(f"Failed to get user uploads: {e}")
            return []

    @staticmethod
    async def get_upload_by_identifier(pdf_identifier: str) -> Optional[Dict]:
        """Get a single upload by its logical PDF identifier."""
        try:
            upload = await mongodb.db.uploaded_pdfs.find_one({'pdf_identifier': pdf_identifier})
            if upload:
                upload['id'] = str(upload['_id'])
            return upload
        except Exception as e:
            logger.error(f"Failed to get upload by identifier: {e}")
            return None

# Create singleton instances
mongodb = MongoDB()
session_db = SessionDB()
user_db = UserDB()
activity_db = UserActivityDB()
pdf_upload_db = PDFUploadDB()
