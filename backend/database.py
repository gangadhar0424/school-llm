"""
MongoDB database connection and models for School LLM
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from typing import Optional, List, Dict, ClassVar, Any, Union
from datetime import datetime, timedelta
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
    # ERP user mirror (Phase 1 school views)
    # ------------------------------------------------------------------
    @staticmethod
    async def upsert_from_ctx(ctx) -> None:
        """Mirror a UserCtx (typically from an ERP `/me/` response) into the
        local `users` collection so admin listing endpoints have something
        to query without re-hitting the ERP per request.

        Behaviour:
        - Upsert keyed on email.
        - `created_at` is only set on insert (preserved across updates).
        - `last_login_at` is bumped on every call.
        - Auth-source / school / role / class / subject fields are refreshed
          so the mirror always tracks the ERP's view of the user.
        """
        try:
            email = (ctx.email or "").strip().lower()
            if not email:
                return
            now = datetime.utcnow()
            set_fields = {
                "email": email,
                "username": ctx.username or email.split("@")[0],
                "full_name": ctx.full_name,
                "role": ctx.role,
                "role_names": list(ctx.role_names or []),
                "erp_title": ctx.erp_title,
                "is_admin": bool(ctx.is_admin),
                "is_school_admin": bool(ctx.is_school_admin),
                "is_superuser": bool(ctx.is_superuser),
                "is_active": bool(ctx.is_active),
                "school_id": ctx.school_id,
                "school_name": ctx.school_name,
                "llm_enabled": bool(ctx.llm_enabled),
                "class_level": ctx.class_level,
                "section": ctx.section,
                "class_section": ctx.class_section,
                "subjects_taught": list(ctx.subjects_taught or []),
                "assigned_classes": list(ctx.assigned_classes or []),
                "must_change_password": bool(ctx.must_change_password),
                "auth_source": ctx.auth_source,
                "erp_user_id": ctx.user_id if ctx.auth_source == "eskoolia" else None,
                "last_login_at": now,
                "updated_at": now,
            }
            await mongodb.db.users.update_one(
                {"email": email},
                {
                    "$set": set_fields,
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Failed to upsert user mirror for {getattr(ctx, 'email', '?')}: {e}")

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
        stored_filename: str = None,
        total_pages: int = 0,
        total_chunks: int = 0,
        total_chars: int = 0,
    ) -> str:
        """Log a PDF upload.

        The `total_*` counts default to 0 so older callers stay
        source-compatible, but new callers should pass real values from
        the PDF handler so admins see meaningful Pages/Chunks in the
        admin table immediately, without needing the migration script
        to retro-fill them.
        """
        try:
            now = datetime.utcnow()
            pdf_record = {
                'filename': filename,
                'file_size': file_size,
                'uploader_email': uploader_email,
                'upload_date': now,
                # Mirror upload_date into uploaded_at so direct Mongo
                # consumers can use either field name -- same dual-name
                # contract the backfill script established.
                'uploaded_at': now,
                'pdf_identifier': pdf_identifier or f"upload_{filename}",
                'stored_filename': stored_filename,
                'total_pages': int(total_pages or 0),
                'total_chunks': int(total_chunks or 0),
                'total_chars': int(total_chars or 0),
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

    @staticmethod
    async def reset_role(role: str) -> bool:
        """Drop every override for a role so the merge in `get_all` falls
        back to ``DEFAULT_PERMISSIONS`` for that role.

        Implemented as a single delete (rather than blanking the perms
        sub-doc) so subsequent reads naturally re-render the canonical
        defaults without leaving a stale ``perms: {}`` artifact around.
        """
        try:
            await mongodb.db.role_permissions.delete_one({"role": role})
            return True
        except Exception as e:
            logger.error(f"Failed to reset permissions for role {role}: {e}")
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


class SchoolAdminDB:
    """Read-only queries that power the school-shaped admin views.

    The lists below are sourced from the local `users` collection — which
    is populated for ERP accounts by `UserDB.upsert_from_ctx` on every
    login. That means these queries only see ERP users who have actually
    signed in at least once. Acknowledged limitation; we'll switch to a
    direct ERP listing endpoint if the ERP team exposes one.
    """

    # Activity types that count toward "AI usage". Kept in sync with the
    # AnalyticsDB metrics list + the teacher question-generation flows.
    AI_ACTIVITY_TYPES = [
        "qa", "summary", "quiz", "audio", "video",
        "short_answer", "long_answer", "mcq",
        "fill_in_blank", "true_false", "question_paper",
    ]

    @staticmethod
    def _school_filter(school_id: Optional[int]) -> Dict[str, Any]:
        """Scope queries by the admin's school. Local-mode admins
        (`school_id=None`) see everything; ERP-mode admins see only
        their tenant."""
        return {"school_id": school_id} if school_id is not None else {}

    @staticmethod
    async def _ai_sessions_by_email(
        emails: List[str], since: datetime
    ) -> Dict[str, int]:
        """For each email in `emails`, count AI-feature activities since
        `since`. Returns {email: count}. One aggregation round-trip."""
        if not emails:
            return {}
        try:
            pipeline = [
                {"$match": {
                    "user_email": {"$in": emails},
                    "activity_type": {"$in": SchoolAdminDB.AI_ACTIVITY_TYPES},
                    "timestamp": {"$gte": since},
                }},
                {"$group": {"_id": "$user_email", "count": {"$sum": 1}}},
            ]
            cursor = mongodb.db.user_activity.aggregate(pipeline)
            rows = await cursor.to_list(length=None)
            return {r["_id"]: r["count"] for r in rows}
        except Exception as e:
            logger.error(f"_ai_sessions_by_email failed: {e}")
            return {}

    @staticmethod
    async def _last_activity_by_email(emails: List[str]) -> Dict[str, datetime]:
        """For each email, the most recent activity timestamp (any type)."""
        if not emails:
            return {}
        try:
            pipeline = [
                {"$match": {"user_email": {"$in": emails}}},
                {"$group": {"_id": "$user_email", "ts": {"$max": "$timestamp"}}},
            ]
            cursor = mongodb.db.user_activity.aggregate(pipeline)
            rows = await cursor.to_list(length=None)
            return {r["_id"]: r["ts"] for r in rows}
        except Exception as e:
            logger.error(f"_last_activity_by_email failed: {e}")
            return {}

    @staticmethod
    async def school_overview(school_id: Optional[int]) -> Dict[str, Any]:
        """Headline counts + top-5 active teachers/students + 14-day daily
        active-user series. Powers /api/admin/school/overview, which is
        the lobby screen for the admin dashboard."""
        try:
            base = SchoolAdminDB._school_filter(school_id)
            now = datetime.utcnow()
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)

            teacher_count = await mongodb.db.users.count_documents(
                {**base, "role": "teacher"}
            )
            student_count = await mongodb.db.users.count_documents(
                {**base, "role": "student"}
            )
            never_logged_in = await mongodb.db.users.count_documents(
                {**base, "last_login_at": None}
            )

            # Pull users in scope once with the fields we'll need later
            # (email for joining against activity; full_name for top-5
            # display labels; role for splitting teachers vs students).
            cursor = mongodb.db.users.find(
                base,
                {"email": 1, "full_name": 1, "username": 1, "role": 1, "class_section": 1},
            )
            user_rows = await cursor.to_list(length=None)
            emails = [u["email"] for u in user_rows]
            label_by_email = {
                u["email"]: (u.get("full_name") or u.get("username") or u["email"])
                for u in user_rows
            }
            class_by_email = {
                u["email"]: u.get("class_section") for u in user_rows
            }
            id_by_email = {u["email"]: str(u["_id"]) for u in user_rows}
            role_by_email = {u["email"]: u.get("role") for u in user_rows}

            active_7d = await mongodb.db.user_activity.aggregate([
                {"$match": {"user_email": {"$in": emails}, "timestamp": {"$gte": week_ago}}},
                {"$group": {"_id": "$user_email"}},
                {"$count": "n"},
            ]).to_list(length=1)
            active_30d = await mongodb.db.user_activity.aggregate([
                {"$match": {"user_email": {"$in": emails}, "timestamp": {"$gte": month_ago}}},
                {"$group": {"_id": "$user_email"}},
                {"$count": "n"},
            ]).to_list(length=1)

            # ── Top-5 most active teachers & students (last 7 days) ────
            # One aggregation, partitioned by role afterwards — cheaper
            # than two round trips and the absolute count is what we
            # need to rank by ("most active this week").
            top_pipeline = [
                {"$match": {
                    "user_email": {"$in": emails},
                    "activity_type": {"$in": SchoolAdminDB.AI_ACTIVITY_TYPES},
                    "timestamp": {"$gte": week_ago},
                }},
                {"$group": {"_id": "$user_email", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            top_rows = await mongodb.db.user_activity.aggregate(top_pipeline).to_list(length=None)
            top_teachers: List[Dict[str, Any]] = []
            top_students: List[Dict[str, Any]] = []
            for row in top_rows:
                em = row["_id"]
                r = role_by_email.get(em)
                entry = {
                    "id": id_by_email.get(em),
                    "email": em,
                    "full_name": label_by_email.get(em, em),
                    "ai_sessions_7d": int(row["count"]),
                }
                if r == "teacher" and len(top_teachers) < 5:
                    top_teachers.append(entry)
                elif r == "student" and len(top_students) < 5:
                    entry["class_section"] = class_by_email.get(em)
                    top_students.append(entry)
                if len(top_teachers) >= 5 and len(top_students) >= 5:
                    break

            # ── 14-day daily-active-users series ───────────────────────
            # 14 days ENDING TODAY (so the rightmost bar on the sparkline
            # is the user's "now" reference). The window starts 13 days
            # before today; iterating 14 days from there gives us today
            # as the last bucket.
            window_start = now - timedelta(days=13)
            dau_rows = await mongodb.db.user_activity.aggregate([
                {"$match": {
                    "user_email": {"$in": emails},
                    "timestamp": {"$gte": window_start},
                }},
                {"$group": {
                    "_id": {
                        "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                        "email": "$user_email",
                    },
                }},
                {"$group": {
                    "_id": "$_id.day",
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ]).to_list(length=None)
            dau_by_day = {r["_id"]: int(r["count"]) for r in dau_rows}
            # Fill in zero-buckets so the sparkline doesn't lie.
            daily_active_14d: List[Dict[str, Any]] = []
            for i in range(14):
                day = (window_start + timedelta(days=i)).strftime("%Y-%m-%d")
                daily_active_14d.append({"date": day, "count": dau_by_day.get(day, 0)})

            # School name — pull from any user in scope, since it's denormalized
            # onto every mirrored doc.
            sample = await mongodb.db.users.find_one(base, {"school_name": 1})

            return {
                "school_id": school_id,
                "school_name": (sample or {}).get("school_name"),
                "counts": {
                    "teachers": teacher_count,
                    "students": student_count,
                    "active_7d": active_7d[0]["n"] if active_7d else 0,
                    "active_30d": active_30d[0]["n"] if active_30d else 0,
                    "never_logged_in": never_logged_in,
                },
                "top_teachers_7d": top_teachers,
                "top_students_7d": top_students,
                "daily_active_14d": daily_active_14d,
            }
        except Exception as e:
            logger.error(f"school_overview failed: {e}")
            return {
                "school_id": school_id,
                "school_name": None,
                "counts": {},
                "top_teachers_7d": [],
                "top_students_7d": [],
                "daily_active_14d": [],
            }

    @staticmethod
    async def list_teachers(school_id: Optional[int]) -> List[Dict[str, Any]]:
        """List teachers in scope, augmented with last_active + AI usage."""
        try:
            base = SchoolAdminDB._school_filter(school_id)
            cursor = mongodb.db.users.find({**base, "role": "teacher"})
            rows = await cursor.to_list(length=None)
            emails = [r["email"] for r in rows]
            month_ago = datetime.utcnow() - timedelta(days=30)
            ai_counts = await SchoolAdminDB._ai_sessions_by_email(emails, month_ago)
            last_seen = await SchoolAdminDB._last_activity_by_email(emails)
            out: List[Dict[str, Any]] = []
            for r in rows:
                em = r.get("email", "")
                out.append({
                    "id": str(r["_id"]),
                    "email": em,
                    "full_name": r.get("full_name") or r.get("username") or em,
                    "erp_title": r.get("erp_title"),
                    "assigned_classes": list(r.get("assigned_classes") or []),
                    "subjects_taught": list(r.get("subjects_taught") or []),
                    "last_active": last_seen.get(em),
                    "ai_sessions_30d": int(ai_counts.get(em, 0)),
                })
            out.sort(key=lambda x: (x["last_active"] or datetime.min), reverse=True)
            return out
        except Exception as e:
            logger.error(f"list_teachers failed: {e}")
            return []

    @staticmethod
    async def list_students(school_id: Optional[int]) -> List[Dict[str, Any]]:
        """List students in scope, augmented with class teacher + AI usage."""
        try:
            base = SchoolAdminDB._school_filter(school_id)
            student_cursor = mongodb.db.users.find({**base, "role": "student"})
            students = await student_cursor.to_list(length=None)
            emails = [s["email"] for s in students]
            month_ago = datetime.utcnow() - timedelta(days=30)
            ai_counts = await SchoolAdminDB._ai_sessions_by_email(emails, month_ago)
            last_seen = await SchoolAdminDB._last_activity_by_email(emails)

            # Build a class_section → class-teacher map. With the current ERP
            # payload we can't distinguish class teacher vs subject teacher,
            # so we pick the first teacher whose `assigned_classes` contains
            # the student's class. Once the ERP exposes a `class_teacher_for`
            # field, swap this for an exact match.
            t_cursor = mongodb.db.users.find(
                {**base, "role": "teacher"},
                {"full_name": 1, "username": 1, "email": 1, "assigned_classes": 1},
            )
            teachers = await t_cursor.to_list(length=None)
            class_to_teacher: Dict[str, Dict[str, Any]] = {}
            for t in teachers:
                name = t.get("full_name") or t.get("username") or t.get("email")
                for cs in (t.get("assigned_classes") or []):
                    class_to_teacher.setdefault(cs, {"id": str(t["_id"]), "name": name})

            out: List[Dict[str, Any]] = []
            for s in students:
                em = s.get("email", "")
                cs = s.get("class_section")
                ct = class_to_teacher.get(cs) if cs else None
                out.append({
                    "id": str(s["_id"]),
                    "email": em,
                    "full_name": s.get("full_name") or s.get("username") or em,
                    "class_section": cs,
                    "class_teacher_id": (ct or {}).get("id"),
                    "class_teacher_name": (ct or {}).get("name"),
                    "last_active": last_seen.get(em),
                    "ai_sessions_30d": int(ai_counts.get(em, 0)),
                })
            out.sort(key=lambda x: (x["last_active"] or datetime.min), reverse=True)
            return out
        except Exception as e:
            logger.error(f"list_students failed: {e}")
            return []

    @staticmethod
    async def lookup_by_email(school_id: Optional[int], email: str) -> Optional[Dict[str, Any]]:
        """Resolve `email` to `{id, role, full_name, school_id}` so the
        Activity feed can route a row click to the right drilldown page
        (Teachers vs Students) without hard-coding the user's role on
        the client. Scoped to the admin's school."""
        try:
            base = SchoolAdminDB._school_filter(school_id)
            doc = await mongodb.db.users.find_one(
                {**base, "email": (email or "").strip().lower()},
                {"full_name": 1, "username": 1, "role": 1, "erp_title": 1, "school_id": 1},
            )
            if not doc:
                return None
            return {
                "id": str(doc["_id"]),
                "email": email,
                "role": doc.get("role"),
                "erp_title": doc.get("erp_title"),
                "full_name": doc.get("full_name") or doc.get("username") or email,
                "school_id": doc.get("school_id"),
            }
        except Exception as e:
            logger.error(f"lookup_by_email failed: {e}")
            return None

    @staticmethod
    async def teacher_detail(school_id: Optional[int], teacher_id: str) -> Optional[Dict[str, Any]]:
        """Profile + roster + per-feature AI usage breakdown for one teacher."""
        try:
            from bson import ObjectId
            base = SchoolAdminDB._school_filter(school_id)
            try:
                _id = ObjectId(teacher_id)
            except Exception:
                return None
            t = await mongodb.db.users.find_one({**base, "_id": _id, "role": "teacher"})
            if not t:
                return None
            classes = list(t.get("assigned_classes") or [])
            # Roster: students in this teacher's classes (within school scope).
            roster_cursor = mongodb.db.users.find(
                {**base, "role": "student", "class_section": {"$in": classes}} if classes
                else {"_id": None},
                {"full_name": 1, "username": 1, "email": 1, "class_section": 1},
            )
            roster_docs = await roster_cursor.to_list(length=None)
            roster = [{
                "id": str(r["_id"]),
                "full_name": r.get("full_name") or r.get("username") or r.get("email"),
                "class_section": r.get("class_section"),
            } for r in roster_docs]

            # Per-feature usage in the last 30 days.
            month_ago = datetime.utcnow() - timedelta(days=30)
            cursor = mongodb.db.user_activity.aggregate([
                {"$match": {
                    "user_email": t["email"],
                    "activity_type": {"$in": SchoolAdminDB.AI_ACTIVITY_TYPES},
                    "timestamp": {"$gte": month_ago},
                }},
                {"$group": {"_id": "$activity_type", "count": {"$sum": 1}}},
            ])
            feature_rows = await cursor.to_list(length=None)
            ai_usage = {row["_id"]: row["count"] for row in feature_rows}
            for at in SchoolAdminDB.AI_ACTIVITY_TYPES:
                ai_usage.setdefault(at, 0)

            return {
                "teacher": {
                    "id": str(t["_id"]),
                    "email": t.get("email"),
                    "full_name": t.get("full_name") or t.get("username") or t.get("email"),
                    "erp_title": t.get("erp_title"),
                    "assigned_classes": classes,
                    "subjects_taught": list(t.get("subjects_taught") or []),
                    "school_id": t.get("school_id"),
                    "school_name": t.get("school_name"),
                    "last_login_at": t.get("last_login_at"),
                },
                "roster": roster,
                "ai_usage": ai_usage,
            }
        except Exception as e:
            logger.error(f"teacher_detail failed: {e}")
            return None

    @staticmethod
    async def student_detail(school_id: Optional[int], student_id: str) -> Optional[Dict[str, Any]]:
        """Profile + class/subject teachers + 14-day activity timeline."""
        try:
            from bson import ObjectId
            base = SchoolAdminDB._school_filter(school_id)
            try:
                _id = ObjectId(student_id)
            except Exception:
                return None
            s = await mongodb.db.users.find_one({**base, "_id": _id, "role": "student"})
            if not s:
                return None
            cs = s.get("class_section")
            class_teacher = None
            subject_teachers: List[Dict[str, Any]] = []
            if cs:
                t_cursor = mongodb.db.users.find(
                    {**base, "role": "teacher", "assigned_classes": cs},
                    {"full_name": 1, "username": 1, "email": 1, "subjects_taught": 1},
                )
                teachers = await t_cursor.to_list(length=None)
                for t in teachers:
                    name = t.get("full_name") or t.get("username") or t.get("email")
                    subjects = list(t.get("subjects_taught") or [])
                    entry = {"id": str(t["_id"]), "full_name": name, "subjects": subjects}
                    subject_teachers.append(entry)
                # Pick the first as class teacher until ERP exposes the field.
                if subject_teachers:
                    ct = subject_teachers[0]
                    class_teacher = {"id": ct["id"], "full_name": ct["full_name"]}

            # 14-day per-day activity counts (any type).
            now = datetime.utcnow()
            two_weeks = now - timedelta(days=14)
            cursor = mongodb.db.user_activity.aggregate([
                {"$match": {"user_email": s["email"], "timestamp": {"$gte": two_weeks}}},
                {"$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}
                    },
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id": 1}},
            ])
            day_rows = await cursor.to_list(length=None)
            timeline = [{"date": d["_id"], "count": d["count"]} for d in day_rows]

            return {
                "student": {
                    "id": str(s["_id"]),
                    "email": s.get("email"),
                    "full_name": s.get("full_name") or s.get("username") or s.get("email"),
                    "class_section": cs,
                    "school_id": s.get("school_id"),
                    "school_name": s.get("school_name"),
                    "last_login_at": s.get("last_login_at"),
                },
                "class_teacher": class_teacher,
                "subject_teachers": subject_teachers,
                "activity_timeline": timeline,
            }
        except Exception as e:
            logger.error(f"student_detail failed: {e}")
            return None

    @staticmethod
    async def relationships(school_id: Optional[int]) -> Dict[str, Any]:
        """Adjacency list for the org-chart view: teachers, classes, and the
        teacher↔class edges (one edge per (teacher, class) pair, carrying
        the subjects that teacher teaches)."""
        try:
            base = SchoolAdminDB._school_filter(school_id)
            t_cursor = mongodb.db.users.find(
                {**base, "role": "teacher"},
                {"full_name": 1, "username": 1, "email": 1,
                 "assigned_classes": 1, "subjects_taught": 1, "erp_title": 1},
            )
            t_docs = await t_cursor.to_list(length=None)
            teachers = []
            classes: set = set()
            edges = []
            for t in t_docs:
                tid = str(t["_id"])
                name = t.get("full_name") or t.get("username") or t.get("email")
                t_classes = list(t.get("assigned_classes") or [])
                subjects = list(t.get("subjects_taught") or [])
                teachers.append({
                    "id": tid,
                    "full_name": name,
                    "erp_title": t.get("erp_title"),
                    "assigned_classes": t_classes,
                    "subjects_taught": subjects,
                })
                for cs in t_classes:
                    classes.add(cs)
                    edges.append({
                        "teacher_id": tid,
                        "class_section": cs,
                        "subjects": subjects,
                    })
            return {
                "teachers": teachers,
                "classes": sorted(classes),
                "edges": edges,
            }
        except Exception as e:
            logger.error(f"relationships failed: {e}")
            return {"teachers": [], "classes": [], "edges": []}


# Create singleton instances
mongodb = MongoDB()
session_db = SessionDB()
user_db = UserDB()
activity_db = UserActivityDB()
pdf_upload_db = PDFUploadDB()
chat_history_db = ChatHistoryDB()
chat_session_db = ChatSessionDB()
analytics_db = AnalyticsDB()
school_admin_db = SchoolAdminDB()
assignment_db = AssignmentDB()
submission_db = SubmissionDB()
role_permissions_db = RolePermissionsDB()
notifications_db = NotificationsDB()
chat_messages_db = ChatMessagesDB()
