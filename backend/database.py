"""
MongoDB database connection and models for School LLM
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from typing import Optional, List, Dict, ClassVar, Any, Union
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
            # Notifications: list-by-user (newest first) + unread count
            await cls._db.notifications.create_index(
                [("user_id", 1), ("created_at", -1)],
                name="notif_user_recent",
            )
            await cls._db.notifications.create_index(
                [("user_id", 1), ("is_read", 1)],
                name="notif_user_unread",
            )
            # Chat: thread fetch (both directions) + unread by recipient
            await cls._db.chat_messages.create_index(
                [("from_user_id", 1), ("to_user_id", 1), ("created_at", 1)],
                name="chat_pair_chrono",
            )
            await cls._db.chat_messages.create_index(
                [("to_user_id", 1), ("is_read", 1)],
                name="chat_recipient_unread",
            )
            logger.info("Database indexes created")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")

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

    # ------------------------------------------------------------------
    # Grade-aware hierarchy helpers (Phase 1)
    # ------------------------------------------------------------------
    @staticmethod
    async def update_user_class(user_id: str, class_level: int, section: str) -> bool:
        """Set a student's class_level (1-10) and section (A/B/C)."""
        try:
            from bson import ObjectId
            result = await mongodb.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'class_level': int(class_level),
                    'section': str(section).upper(),
                    'class_section': f"{int(class_level)}{str(section).upper()}",
                }}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update user class: {e}")
            return False

    @staticmethod
    async def assign_teacher(user_id: str, subjects: list, classes: list) -> bool:
        """Set a teacher's subjects_taught + assigned_classes (e.g. ['5A','6A'])."""
        try:
            from bson import ObjectId
            normalized = [str(c).strip().upper().replace(" ", "") for c in (classes or [])]
            result = await mongodb.db.users.update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'subjects_taught': list(subjects or []),
                    'assigned_classes': normalized,
                }}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to assign teacher: {e}")
            return False

    @staticmethod
    async def get_teachers_for_class(class_section: str, subject: Optional[str] = None) -> list:
        """Find teachers assigned to a given class+section (e.g. '5A').
        Optionally filter by subject."""
        try:
            cs = (class_section or "").strip().upper().replace(" ", "")
            query: Dict = {
                'role': 'teacher',
                'assigned_classes': cs,
            }
            if subject:
                query['subjects_taught'] = subject
            cursor = mongodb.db.users.find(query)
            out = []
            async for u in cursor:
                u['id'] = str(u['_id'])
                u.pop('hashed_password', None)
                out.append(u)
            return out
        except Exception as e:
            logger.error(f"Failed to find teachers for class: {e}")
            return []

    @staticmethod
    async def list_users(role: Optional[str] = None) -> list:
        """List users, optionally filtered by role."""
        try:
            query: Dict = {}
            if role:
                query['role'] = role
            cursor = mongodb.db.users.find(query)
            out = []
            async for u in cursor:
                u['id'] = str(u['_id'])
                u.pop('hashed_password', None)
                out.append(u)
            return out
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []


# ───────────────────────────────────────────────────────────────────────────
# Assignment + Submission collections (teacher → students workflow)
# ───────────────────────────────────────────────────────────────────────────
class AssignmentDB:
    """CRUD on the `assignments` collection.

    Document shape:
      {
        _id, teacher_email, teacher_id, title, description,
        class_section, subject, questions: [...], due_date,
        status: "draft"|"published"|"closed",
        created_at, updated_at, published_at
      }
    """

    @staticmethod
    async def create(doc: Dict) -> Optional[str]:
        try:
            doc = dict(doc)
            doc["created_at"] = datetime.utcnow()
            doc["updated_at"] = doc["created_at"]
            res = await mongodb.db.assignments.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logger.error(f"AssignmentDB.create failed: {e}")
            return None

    @staticmethod
    async def get(assignment_id: str) -> Optional[Dict]:
        try:
            from bson import ObjectId
            d = await mongodb.db.assignments.find_one({"_id": ObjectId(assignment_id)})
            if d:
                d["id"] = str(d["_id"])
            return d
        except Exception as e:
            logger.error(f"AssignmentDB.get failed: {e}")
            return None

    @staticmethod
    async def list_by_teacher(teacher_email: str) -> list:
        try:
            cursor = mongodb.db.assignments.find({"teacher_email": teacher_email})
            out = []
            async for d in cursor:
                d["id"] = str(d["_id"])
                out.append(d)
            return sorted(out, key=lambda x: x.get("created_at") or datetime.min, reverse=True)
        except Exception as e:
            logger.error(f"AssignmentDB.list_by_teacher failed: {e}")
            return []

    @staticmethod
    async def list_for_class(class_section: str, only_published: bool = True) -> list:
        try:
            query: Dict = {"class_section": class_section}
            if only_published:
                query["status"] = "published"
            cursor = mongodb.db.assignments.find(query)
            out = []
            async for d in cursor:
                d["id"] = str(d["_id"])
                out.append(d)
            return sorted(out, key=lambda x: x.get("published_at") or x.get("created_at") or datetime.min, reverse=True)
        except Exception as e:
            logger.error(f"AssignmentDB.list_for_class failed: {e}")
            return []

    @staticmethod
    async def update(assignment_id: str, update_doc: Dict) -> bool:
        try:
            from bson import ObjectId
            update_doc = dict(update_doc)
            update_doc["updated_at"] = datetime.utcnow()
            if update_doc.get("status") == "published":
                update_doc.setdefault("published_at", datetime.utcnow())
            res = await mongodb.db.assignments.update_one(
                {"_id": ObjectId(assignment_id)},
                {"$set": update_doc},
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"AssignmentDB.update failed: {e}")
            return False

    @staticmethod
    async def delete(assignment_id: str) -> bool:
        try:
            from bson import ObjectId
            res = await mongodb.db.assignments.delete_one({"_id": ObjectId(assignment_id)})
            return res.deleted_count > 0
        except Exception as e:
            logger.error(f"AssignmentDB.delete failed: {e}")
            return False


class SubmissionDB:
    """CRUD on the `submissions` collection.

    Document shape:
      {
        _id, assignment_id, student_email, student_id, class_section,
        answers: [{
            question_index, student_answer, ai_score, ai_method,
            ai_band, marks, scaled_score, kw_summary, feedback,
            teacher_override: {score, comment, by, at}
        }],
        total_score, total_max, percent,
        submitted_at, graded_at
      }
    """

    @staticmethod
    async def create(doc: Dict) -> Optional[str]:
        try:
            doc = dict(doc)
            doc["submitted_at"] = datetime.utcnow()
            doc["graded_at"] = doc["submitted_at"]
            res = await mongodb.db.submissions.insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logger.error(f"SubmissionDB.create failed: {e}")
            return None

    @staticmethod
    async def get(submission_id: str) -> Optional[Dict]:
        try:
            from bson import ObjectId
            d = await mongodb.db.submissions.find_one({"_id": ObjectId(submission_id)})
            if d:
                d["id"] = str(d["_id"])
            return d
        except Exception as e:
            logger.error(f"SubmissionDB.get failed: {e}")
            return None

    @staticmethod
    async def get_by_student_and_assignment(
        student_email: str, assignment_id: str
    ) -> Optional[Dict]:
        try:
            d = await mongodb.db.submissions.find_one({
                "student_email": student_email,
                "assignment_id": assignment_id,
            })
            if d:
                d["id"] = str(d["_id"])
            return d
        except Exception as e:
            logger.error(f"SubmissionDB.get_by_student_and_assignment failed: {e}")
            return None

    @staticmethod
    async def list_for_assignment(assignment_id: str) -> list:
        try:
            cursor = mongodb.db.submissions.find({"assignment_id": assignment_id})
            out = []
            async for d in cursor:
                d["id"] = str(d["_id"])
                out.append(d)
            return sorted(out, key=lambda x: x.get("submitted_at") or datetime.min, reverse=True)
        except Exception as e:
            logger.error(f"SubmissionDB.list_for_assignment failed: {e}")
            return []

    @staticmethod
    async def list_for_student(student_email: str) -> list:
        try:
            cursor = mongodb.db.submissions.find({"student_email": student_email})
            out = []
            async for d in cursor:
                d["id"] = str(d["_id"])
                out.append(d)
            return sorted(out, key=lambda x: x.get("submitted_at") or datetime.min, reverse=True)
        except Exception as e:
            logger.error(f"SubmissionDB.list_for_student failed: {e}")
            return []

    @staticmethod
    async def list_for_student_and_teacher(
        student_email: str, teacher_email: str
    ) -> list:
        """List submissions where the assignment was created by the given
        teacher AND submitted by the given student (for the teacher's
        per-student-history view)."""
        try:
            # Two-step: find assignment ids for this teacher, then submissions.
            t_assignments = mongodb.db.assignments.find(
                {"teacher_email": teacher_email}, {"_id": 1}
            )
            assignment_ids = [str(a["_id"]) async for a in t_assignments]
            if not assignment_ids:
                return []
            cursor = mongodb.db.submissions.find({
                "student_email": student_email,
                "assignment_id": {"$in": assignment_ids},
            })
            out = []
            async for d in cursor:
                d["id"] = str(d["_id"])
                out.append(d)
            return sorted(out, key=lambda x: x.get("submitted_at") or datetime.min, reverse=True)
        except Exception as e:
            logger.error(f"SubmissionDB.list_for_student_and_teacher failed: {e}")
            return []

    @staticmethod
    async def override_grade(
        submission_id: str,
        question_index: int,
        score: float,
        comment: str,
        by: str,
    ) -> Optional[Dict]:
        """Set a teacher override on a single answer and recompute totals.
        Returns the updated submission document, or None on failure."""
        try:
            from bson import ObjectId
            sub = await mongodb.db.submissions.find_one({"_id": ObjectId(submission_id)})
            if not sub:
                return None
            answers = sub.get("answers") or []
            if question_index < 0 or question_index >= len(answers):
                return None

            ans = answers[question_index]
            marks = float(ans.get("marks") or 10)
            # Override score is stored on a 0-10 scale; scale to marks for totals.
            score = max(0.0, min(10.0, float(score)))
            ans["teacher_override"] = {
                "score": round(score, 1),
                "comment": comment or "",
                "by": by,
                "at": datetime.utcnow(),
            }
            # Effective scaled score = override (0-10) * marks / 10
            ans["scaled_score"] = round(score * marks / 10.0, 2)
            answers[question_index] = ans

            total = sum(float(a.get("scaled_score") or 0) for a in answers)
            total_max = sum(float(a.get("marks") or 0) for a in answers)
            percent = round((total / total_max * 100), 1) if total_max else 0.0

            await mongodb.db.submissions.update_one(
                {"_id": ObjectId(submission_id)},
                {"$set": {
                    "answers": answers,
                    "total_score": round(total, 2),
                    "total_max": round(total_max, 2),
                    "percent": percent,
                    "graded_at": datetime.utcnow(),
                }},
            )
            sub = await mongodb.db.submissions.find_one({"_id": ObjectId(submission_id)})
            if sub:
                sub["id"] = str(sub["_id"])
            return sub
        except Exception as e:
            logger.error(f"SubmissionDB.override_grade failed: {e}")
            return None


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
                    'role': user.get('role') or ('admin' if user.get('is_admin') else 'student'),
                    'is_admin': user.get('is_admin', False),
                    'is_active': user.get('is_active', True),
                    'class_level': user.get('class_level'),
                    'section': user.get('section'),
                    'class_section': user.get('class_section'),
                    'subjects_taught': user.get('subjects_taught') or [],
                    'assigned_classes': user.get('assigned_classes') or [],
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

class ChatHistoryDB:
    """Chat history persistence for Q&A conversations."""

    @staticmethod
    async def save_message(
        user_email: str,
        document_ids: List[str],
        question: str,
        answer: str,
        sources: List[str] = None,
        confidence: str = "medium",
    ) -> str:
        try:
            record = {
                "user_email": user_email,
                "document_ids": document_ids,
                "question": question,
                "answer": answer,
                "sources": sources or [],
                "confidence": confidence,
                "timestamp": datetime.utcnow(),
            }
            result = await mongodb.db.chat_history.insert_one(record)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to save chat message: {e}")
            return None

    @staticmethod
    async def get_history(
        user_email: str,
        document_id: str = None,
        limit: int = 50,
    ) -> List[Dict]:
        try:
            query: Dict[str, Any] = {"user_email": user_email}
            if document_id:
                query["document_ids"] = {"$in": [document_id]}
            cursor = (
                mongodb.db.chat_history.find(query)
                .sort("timestamp", -1)
                .limit(limit)
            )
            records = await cursor.to_list(length=None)
            for r in records:
                r["id"] = str(r["_id"])
                del r["_id"]
            records.reverse()  # oldest first for chat display
            return records
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return []

    @staticmethod
    async def clear_history(user_email: str, document_id: str = None) -> int:
        try:
            query: Dict[str, Any] = {"user_email": user_email}
            if document_id:
                query["document_ids"] = {"$in": [document_id]}
            result = await mongodb.db.chat_history.delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"Failed to clear chat history: {e}")
            return 0

    @staticmethod
    async def get_all_history(limit: int = 200) -> List[Dict]:
        try:
            cursor = mongodb.db.chat_history.find().sort("timestamp", -1).limit(limit)
            records = await cursor.to_list(length=None)
            for r in records:
                r["id"] = str(r["_id"])
                del r["_id"]
            return records
        except Exception as e:
            logger.error(f"Failed to get all chat history: {e}")
            return []


class ChatSessionDB:
    """ChatGPT-style persistent chat sessions.

    Each session has its own conversation thread (messages list) and an auto
    generated name. Sessions can be tied to a single PDF, a list of PDFs
    (multi-doc), or no PDF at all.
    """

    @staticmethod
    async def create_session(
        user_email: str,
        pdf_ids: Optional[List[str]] = None,
        mode: str = "single",  # "single" | "multi"
        name: str = "New chat",
    ) -> Optional[str]:
        try:
            now = datetime.utcnow()
            doc = {
                "user_email": user_email,
                "pdf_ids": pdf_ids or [],
                "mode": mode,
                "name": name,
                "created_at": now,
                "updated_at": now,
                "messages": [],
                "auto_named": False,
            }
            result = await mongodb.db.chat_sessions.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to create chat session: {e}")
            return None

    @staticmethod
    async def list_sessions(user_email: str, limit: int = 100) -> List[Dict]:
        try:
            cursor = (
                mongodb.db.chat_sessions.find({"user_email": user_email})
                .sort("updated_at", -1)
                .limit(limit)
            )
            sessions = await cursor.to_list(length=None)
            for s in sessions:
                s["id"] = str(s["_id"])
                del s["_id"]
                s.pop("messages", None)
            return sessions
        except Exception as e:
            logger.error(f"Failed to list chat sessions: {e}")
            return []

    @staticmethod
    async def get_session(session_id: str, user_email: str) -> Optional[Dict]:
        try:
            from bson import ObjectId
            session = await mongodb.db.chat_sessions.find_one({
                "_id": ObjectId(session_id),
                "user_email": user_email,
            })
            if session:
                session["id"] = str(session["_id"])
                del session["_id"]
            return session
        except Exception as e:
            logger.error(f"Failed to get chat session: {e}")
            return None

    @staticmethod
    async def append_message(
        session_id: str,
        user_email: str,
        role: str,
        content: str,
        sources: Optional[List[str]] = None,
    ) -> bool:
        try:
            from bson import ObjectId
            msg = {
                "role": role,
                "content": content,
                "sources": sources or [],
                "timestamp": datetime.utcnow(),
            }
            result = await mongodb.db.chat_sessions.update_one(
                {"_id": ObjectId(session_id), "user_email": user_email},
                {
                    "$push": {"messages": msg},
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to append message: {e}")
            return False

    @staticmethod
    async def rename_session(session_id: str, user_email: str, name: str, auto: bool = False) -> bool:
        try:
            from bson import ObjectId
            update = {"name": name, "updated_at": datetime.utcnow()}
            if auto:
                update["auto_named"] = True
            result = await mongodb.db.chat_sessions.update_one(
                {"_id": ObjectId(session_id), "user_email": user_email},
                {"$set": update},
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to rename session: {e}")
            return False

    @staticmethod
    async def delete_session(session_id: str, user_email: str) -> bool:
        try:
            from bson import ObjectId
            result = await mongodb.db.chat_sessions.delete_one({
                "_id": ObjectId(session_id),
                "user_email": user_email,
            })
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False


class AnalyticsDB:
    """Analytics aggregation for the admin dashboard."""

    @staticmethod
    async def get_metrics() -> Dict:
        try:
            total_users = await mongodb.db.users.count_documents({})
            active_users = await mongodb.db.users.count_documents({"is_active": True})
            total_pdfs = await mongodb.db.uploaded_pdfs.count_documents({})
            total_ai_calls = await mongodb.db.user_activity.count_documents({
                "activity_type": {"$in": ["quiz", "summary", "qa", "audio", "video"]}
            })
            return {
                "total_users": total_users,
                "active_users": active_users,
                "total_pdfs": total_pdfs,
                "total_ai_calls": total_ai_calls,
            }
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {}

    @staticmethod
    async def get_usage_over_time(days: int = 7) -> List[Dict]:
        """Returns daily activity counts for the past N days."""
        try:
            from datetime import timedelta
            result = []
            now = datetime.utcnow()
            for i in range(days - 1, -1, -1):
                day_start = (now - timedelta(days=i)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                day_end = day_start.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
                count = await mongodb.db.user_activity.count_documents({
                    "timestamp": {"$gte": day_start, "$lte": day_end}
                })
                result.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "count": count,
                })
            return result
        except Exception as e:
            logger.error(f"Failed to get usage over time: {e}")
            return []

    @staticmethod
    async def get_feature_usage() -> Dict[str, int]:
        """Returns usage count per AI feature."""
        try:
            features = ["quiz", "summary", "qa", "audio", "video", "pdf_upload", "login"]
            result = {}
            for feature in features:
                count = await mongodb.db.user_activity.count_documents(
                    {"activity_type": feature}
                )
                result[feature] = count
            return result
        except Exception as e:
            logger.error(f"Failed to get feature usage: {e}")
            return {}

    @staticmethod
    async def get_audit_logs(
        user_email: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        limit: int = 500,
    ) -> List[Dict]:
        try:
            query: Dict[str, Any] = {}
            if user_email:
                query["user_email"] = user_email
            if start_date or end_date:
                ts_filter: Dict[str, Any] = {}
                if start_date:
                    ts_filter["$gte"] = start_date
                if end_date:
                    ts_filter["$lte"] = end_date
                query["timestamp"] = ts_filter
            cursor = (
                mongodb.db.user_activity.find(query)
                .sort("timestamp", -1)
                .limit(limit)
            )
            logs = await cursor.to_list(length=None)
            for log in logs:
                log["id"] = str(log["_id"])
                del log["_id"]
            return logs
        except Exception as e:
            logger.error(f"Failed to get audit logs: {e}")
            return []


class RolePermissionsDB:
    """Per-role feature permission overrides. Default is all features enabled.
    Stored as a single document keyed by role: { role: 'admin', perms: {feature: bool} }."""

    DEFAULT_PERMISSIONS = {
        "admin": {
            "view_analytics": True,
            "manage_users": True,
            "toggle_user_status": True,
            "assign_class_section": True,
            "assign_teacher_subjects": True,
            "view_audit_logs": True,
            "export_data": True,
            "upload_pdfs": True,
            "use_ai_tools": True,
            "change_password": True,
        },
        "teacher": {
            "create_assignments": True,
            "edit_assignments": True,
            "override_grading": True,
            "view_submissions": True,
            "upload_pdfs": True,
            "use_ai_tools": True,
            "change_password": True,
        },
        "student": {
            "submit_assignments": True,
            "view_own_grades": True,
            "upload_pdfs": True,
            "use_ai_tools": True,
            "change_password": True,
        },
    }

    @staticmethod
    async def get_all() -> Dict[str, Dict[str, bool]]:
        """Returns the full permission map. Missing entries fall back to defaults (True)."""
        try:
            cursor = mongodb.db.role_permissions.find({})
            docs = await cursor.to_list(length=None)
            stored = {d["role"]: d.get("perms", {}) for d in docs if d.get("role")}

            # Merge defaults with stored overrides (stored wins where set)
            merged: Dict[str, Dict[str, bool]] = {}
            for role, defaults in RolePermissionsDB.DEFAULT_PERMISSIONS.items():
                merged[role] = {**defaults, **(stored.get(role) or {})}
            return merged
        except Exception as e:
            logger.error(f"Failed to get role permissions: {e}")
            return RolePermissionsDB.DEFAULT_PERMISSIONS.copy()

    @staticmethod
    async def is_allowed(role: str, feature: str) -> bool:
        """Check if a role is allowed to access a feature.
        - Explicit override in DB wins.
        - Otherwise, fall back to the role's default in DEFAULT_PERMISSIONS.
        - Features NOT listed in DEFAULT_PERMISSIONS for this role default to True
          (so the existing role-dependency-injected endpoint still gates access)."""
        try:
            doc = await mongodb.db.role_permissions.find_one({"role": role})
            if doc and "perms" in doc and feature in doc["perms"]:
                return bool(doc["perms"][feature])
            # Fall back to default (True if not listed, since the role check
            # itself already gates the endpoint)
            defaults = RolePermissionsDB.DEFAULT_PERMISSIONS.get(role, {})
            return bool(defaults.get(feature, True))
        except Exception as e:
            logger.error(f"Failed to check permission ({role}/{feature}): {e}")
            return True  # fail open — don't break system on DB error

    @staticmethod
    async def set_permission(role: str, feature: str, enabled: bool) -> bool:
        """Update a single permission for a role. Upserts the role document."""
        try:
            await mongodb.db.role_permissions.update_one(
                {"role": role},
                {
                    "$set": {
                        f"perms.{feature}": bool(enabled),
                        "updated_at": datetime.utcnow(),
                    }
                },
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set permission ({role}/{feature}): {e}")
            return False


class NotificationsDB:
    """In-app notifications. Each notification targets a single recipient and
    carries a type tag, short title/body, optional link, and read state.

    Types currently in use:
      - assignment_published: a teacher published an assignment for the
        student's class+section
      - submission_received:  a student submitted a teacher's assignment
      - deadline_today:       NOT stored — synthesized live by the API on
        every fetch from assignments due today that the student has not
        submitted, so they auto-expire when the day rolls over.
    """

    @staticmethod
    async def create(*, user_id: str, type_: str, title: str, body: str,
                     link: Optional[str] = None) -> bool:
        try:
            await mongodb.db.notifications.insert_one({
                "user_id": str(user_id),
                "type": type_,
                "title": title,
                "body": body,
                "link": link,
                "is_read": False,
                "created_at": datetime.utcnow(),
            })
            return True
        except Exception as e:
            logger.error(f"NotificationsDB.create failed: {e}")
            return False

    @staticmethod
    async def create_many(notifications: List[Dict[str, Any]]) -> int:
        """Bulk-insert. Caller is responsible for filling each doc with
        user_id, type, title, body. read state + timestamp are added here."""
        if not notifications:
            return 0
        now = datetime.utcnow()
        docs = [
            {**n, "is_read": False, "created_at": now}
            for n in notifications
        ]
        try:
            result = await mongodb.db.notifications.insert_many(docs)
            return len(result.inserted_ids)
        except Exception as e:
            logger.error(f"NotificationsDB.create_many failed: {e}")
            return 0

    @staticmethod
    async def list_for_user(user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        try:
            cursor = mongodb.db.notifications.find(
                {"user_id": str(user_id)}
            ).sort("created_at", -1).limit(limit)
            out = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                out.append(doc)
            return out
        except Exception as e:
            logger.error(f"NotificationsDB.list_for_user failed: {e}")
            return []

    @staticmethod
    async def unread_count(user_id: str) -> int:
        try:
            return await mongodb.db.notifications.count_documents(
                {"user_id": str(user_id), "is_read": False}
            )
        except Exception as e:
            logger.error(f"NotificationsDB.unread_count failed: {e}")
            return 0

    @staticmethod
    async def mark_read(notification_id: str, user_id: str) -> bool:
        from bson import ObjectId
        try:
            result = await mongodb.db.notifications.update_one(
                {"_id": ObjectId(notification_id), "user_id": str(user_id)},
                {"$set": {"is_read": True}},
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"NotificationsDB.mark_read failed: {e}")
            return False

    @staticmethod
    async def mark_all_read(user_id: str) -> int:
        try:
            result = await mongodb.db.notifications.update_many(
                {"user_id": str(user_id), "is_read": False},
                {"$set": {"is_read": True}},
            )
            return result.modified_count
        except Exception as e:
            logger.error(f"NotificationsDB.mark_all_read failed: {e}")
            return 0


class ChatMessagesDB:
    """1-on-1 chat messages between a teacher and a student.

    Authorization (a teacher↔student pair is allowed to talk) is enforced
    at the route layer using each side's class/subject assignments. This
    DB layer just stores and queries — it does not validate the pairing.
    """

    @staticmethod
    async def send(*, from_user_id: str, from_role: str, from_name: str,
                   to_user_id: str, to_role: str, to_name: str,
                   message: str) -> Optional[Dict[str, Any]]:
        try:
            doc = {
                "from_user_id": str(from_user_id),
                "from_role": from_role,
                "from_name": from_name,
                "to_user_id": str(to_user_id),
                "to_role": to_role,
                "to_name": to_name,
                "message": message.strip(),
                "is_read": False,
                "created_at": datetime.utcnow(),
            }
            result = await mongodb.db.chat_messages.insert_one(doc)
            doc["_id"] = str(result.inserted_id)
            return doc
        except Exception as e:
            logger.error(f"ChatMessagesDB.send failed: {e}")
            return None

    @staticmethod
    async def list_thread(user_a: str, user_b: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Return the messages between two users in chronological order."""
        try:
            cursor = mongodb.db.chat_messages.find({
                "$or": [
                    {"from_user_id": str(user_a), "to_user_id": str(user_b)},
                    {"from_user_id": str(user_b), "to_user_id": str(user_a)},
                ]
            }).sort("created_at", 1).limit(limit)
            out = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                out.append(doc)
            return out
        except Exception as e:
            logger.error(f"ChatMessagesDB.list_thread failed: {e}")
            return []

    @staticmethod
    async def unread_count(user_id: str) -> int:
        """Total unread messages addressed to this user across all threads."""
        try:
            return await mongodb.db.chat_messages.count_documents(
                {"to_user_id": str(user_id), "is_read": False}
            )
        except Exception as e:
            logger.error(f"ChatMessagesDB.unread_count failed: {e}")
            return 0

    @staticmethod
    async def unread_count_from(user_id: str, from_user_id: str) -> int:
        """Unread messages from a specific other user — used to badge a
        contact in the contact list."""
        try:
            return await mongodb.db.chat_messages.count_documents({
                "to_user_id": str(user_id),
                "from_user_id": str(from_user_id),
                "is_read": False,
            })
        except Exception as e:
            logger.error(f"ChatMessagesDB.unread_count_from failed: {e}")
            return 0

    @staticmethod
    async def mark_thread_read(reader_user_id: str, other_user_id: str) -> int:
        """Mark every message FROM other_user_id TO reader_user_id as read.
        Only the recipient can clear unread state on a message."""
        try:
            result = await mongodb.db.chat_messages.update_many(
                {
                    "to_user_id": str(reader_user_id),
                    "from_user_id": str(other_user_id),
                    "is_read": False,
                },
                {"$set": {"is_read": True}},
            )
            return result.modified_count
        except Exception as e:
            logger.error(f"ChatMessagesDB.mark_thread_read failed: {e}")
            return 0

    @staticmethod
    async def last_message_with(user_id: str, other_user_id: str) -> Optional[Dict[str, Any]]:
        """The single most recent message exchanged with another user —
        used to render contact-list previews."""
        try:
            doc = await mongodb.db.chat_messages.find_one(
                {
                    "$or": [
                        {"from_user_id": str(user_id), "to_user_id": str(other_user_id)},
                        {"from_user_id": str(other_user_id), "to_user_id": str(user_id)},
                    ]
                },
                sort=[("created_at", -1)],
            )
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as e:
            logger.error(f"ChatMessagesDB.last_message_with failed: {e}")
            return None


# Create singleton instances
mongodb = MongoDB()
session_db = SessionDB()
user_db = UserDB()
activity_db = UserActivityDB()
pdf_upload_db = PDFUploadDB()
chat_history_db = ChatHistoryDB()
chat_session_db = ChatSessionDB()
analytics_db = AnalyticsDB()
assignment_db = AssignmentDB()
submission_db = SubmissionDB()
role_permissions_db = RolePermissionsDB()
notifications_db = NotificationsDB()
chat_messages_db = ChatMessagesDB()
