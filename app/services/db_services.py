import uuid
import time
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
import logfire

from app.db.models import (
    User,
    Conversation,
    Message,
    MessageCitation,
    MessageFeedback,
    AuditLog,
    DocumentMetadata,
    QueryLog,
)


class DatabasePersistenceService:
    """
    Centralized persistence service layer for MASS QA operations with safe transaction handling.
    Observability & logging failures are caught to ensure normal chatbot operation is never interrupted.
    """

    # --- User Operations ---

    @staticmethod
    def ensure_user(
        db: Session,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: str = "USER"
    ) -> User:
        """
        Ensure user exists in users table before foreign key references.
        """
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user is not None:
                return user

            uname = username or user_id
            uemail = email or f"{user_id}@mass.local"

            # Avoid collision on username or email
            if db.query(User).filter(User.username == uname).first():
                uname = f"{uname}_{uuid.uuid4().hex[:4]}"
            if db.query(User).filter(User.email == uemail).first():
                uemail = f"{uuid.uuid4().hex[:6]}_{uemail}"

            user = User(
                id=user_id,
                username=uname,
                email=uemail,
                display_name=username or user_id,
                password_hash="argon2_system_managed",
                role=role,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        except Exception as e:
            db.rollback()
            # If concurrent insert already created it, try fetching again
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user
            logfire.error(f"Error ensuring user existence: {e}")
            raise

    # --- Conversation Operations ---

    @staticmethod
    def get_or_create_conversation(
        db: Session,
        session_id: str,
        user_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> Conversation:
        try:
            if user_id:
                DatabasePersistenceService.ensure_user(db, user_id=user_id)

            conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
            if conv is not None:
                if user_id and not conv.user_id:
                    conv.user_id = user_id
                    db.commit()
                    db.refresh(conv)
                return conv

            new_conv = Conversation(
                id=str(uuid.uuid4()),
                session_id=session_id,
                user_id=user_id,
                title=title or "New Conversation",
                status="ACTIVE"
            )
            db.add(new_conv)
            db.commit()
            db.refresh(new_conv)
            return new_conv
        except Exception as e:
            db.rollback()
            logfire.error(f"Error getting/creating conversation: {e}")
            raise

    @staticmethod
    def get_conversation_by_id(
        db: Session,
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Conversation]:
        query = db.query(Conversation).filter(Conversation.id == conversation_id)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        return query.first()

    @staticmethod
    def list_user_conversations(
        db: Session,
        user_id: str,
        limit: int = 50
    ) -> List[Conversation]:
        return (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id, Conversation.status != "DELETED")
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def update_conversation_status(
        db: Session,
        conversation_id: str,
        status: str,
        user_id: Optional[str] = None
    ) -> bool:
        try:
            conv = DatabasePersistenceService.get_conversation_by_id(db, conversation_id, user_id=user_id)
            if conv is None:
                return False
            conv.status = status
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logfire.error(f"Error updating conversation status: {e}")
            return False

    # --- Message Operations ---

    @staticmethod
    def create_message(
        db: Session,
        conversation_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
        model_name: Optional[str] = None,
        response_time_ms: Optional[float] = None,
        token_count: Optional[int] = None,
        cache_hit: bool = False,
        status: str = "SUCCESS"
    ) -> Message:
        try:
            if user_id:
                DatabasePersistenceService.ensure_user(db, user_id=user_id)

            msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                user_id=user_id,
                role=role.upper(),
                content=content,
                model_name=model_name,
                response_time_ms=response_time_ms,
                token_count=token_count,
                cache_hit=cache_hit,
                status=status
            )
            db.add(msg)
            # Update last_message_at on conversation
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                conv.last_message_at = func.now()
            db.commit()
            db.refresh(msg)
            return msg
        except Exception as e:
            db.rollback()
            logfire.error(f"Error creating message: {e}")
    @staticmethod
    def get_conversation_messages(
        db: Session,
        conversation_id: str,
        limit: int = 100
    ) -> List[Message]:
        return (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .all()
        )

    # --- Citation Operations ---


    @staticmethod
    def create_citations(
        db: Session,
        message_id: str,
        citations: List[Dict[str, Any]]
    ) -> List[MessageCitation]:
        try:
            citation_records = []
            for cit in citations:
                c_rec = MessageCitation(
                    id=str(uuid.uuid4()),
                    message_id=message_id,
                    document_id=cit.get("document_id"),
                    document_name=cit.get("document_name") or "Unknown Document",
                    source_type=cit.get("content_type") or cit.get("source_type"),
                    page_number=cit.get("page_number"),
                    slide_number=cit.get("slide_number"),
                    chunk_id=cit.get("chunk_id"),
                    score=cit.get("score") or cit.get("relevance_score"),
                    citation_text=cit.get("snippet") or cit.get("preview_text"),
                    metadata_=cit.get("metadata")
                )
                db.add(c_rec)
                citation_records.append(c_rec)
            db.commit()
            return citation_records
        except Exception as e:
            db.rollback()
            logfire.error(f"Error saving message citations: {e}")
            return []

    # --- Feedback Operations ---

    @staticmethod
    def submit_feedback(
        db: Session,
        message_id: str,
        rating: str,
        user_id: Optional[str] = None,
        comment: Optional[str] = None
    ) -> MessageFeedback:
        try:
            if user_id:
                DatabasePersistenceService.ensure_user(db, user_id=user_id)

            fb = db.query(MessageFeedback).filter(MessageFeedback.message_id == message_id).first()
            if fb is not None:
                fb.rating = rating.upper()
                fb.comment = comment
                if user_id:
                    fb.user_id = user_id
                db.commit()
                db.refresh(fb)
                return fb

            new_fb = MessageFeedback(
                id=str(uuid.uuid4()),
                message_id=message_id,
                user_id=user_id,
                rating=rating.upper(),
                comment=comment
            )
            db.add(new_fb)
            db.commit()
            db.refresh(new_fb)
            return new_fb
        except Exception as e:
            db.rollback()
            logfire.error(f"Error saving message feedback: {e}")
            raise

    # --- Audit Logging Operations ---

    @staticmethod
    def log_audit_event(
        db: Session,
        action: str,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        try:
            audit = AuditLog(
                id=str(uuid.uuid4()),
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                endpoint=endpoint,
                http_method=http_method,
                status_code=status_code,
                request_id=request_id,
                session_id=session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata_=metadata
            )
            db.add(audit)
            db.commit()
        except Exception as e:
            db.rollback()
            logfire.warning(f"Audit log write non-fatal error: {e}")

    # --- Query Logging Operations ---

    @staticmethod
    def log_query_metrics(
        db: Session,
        query_text: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        retrieval_time_ms: Optional[float] = None,
        reranking_time_ms: Optional[float] = None,
        llm_time_ms: Optional[float] = None,
        total_time_ms: Optional[float] = None,
        retrieved_count: Optional[int] = None,
        reranked_count: Optional[int] = None,
        cache_hit: bool = False,
        model_name: Optional[str] = None,
        status: str = "SUCCESS",
        error_type: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> None:
        try:
            q_log = QueryLog(
                id=str(uuid.uuid4()),
                user_id=user_id,
                conversation_id=conversation_id,
                message_id=message_id,
                query_text=query_text,
                retrieval_time_ms=retrieval_time_ms,
                reranking_time_ms=reranking_time_ms,
                llm_time_ms=llm_time_ms,
                total_time_ms=total_time_ms,
                retrieved_count=retrieved_count,
                reranked_count=reranked_count,
                cache_hit=cache_hit,
                model_name=model_name,
                status=status,
                error_type=error_type,
                request_id=request_id
            )
            db.add(q_log)
            db.commit()
        except Exception as e:
            db.rollback()
            logfire.warning(f"Query metrics write non-fatal error: {e}")

    # --- Document Metadata Operations ---

    @staticmethod
    def upsert_document_metadata(
        db: Session,
        document_id: str,
        document_name: str,
        file_name: Optional[str] = None,
        file_type: Optional[str] = None,
        version: str = "v1",
        source: Optional[str] = None,
        chunk_count: int = 0,
        page_count: Optional[int] = None,
        slide_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DocumentMetadata:
        try:
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.document_id == document_id).first()
            if doc is not None:
                doc.document_name = document_name
                doc.file_name = file_name or doc.file_name
                doc.file_type = file_type or doc.file_type
                doc.version = version
                doc.source = source or doc.source
                doc.chunk_count = chunk_count
                doc.page_count = page_count or doc.page_count
                doc.slide_count = slide_count or doc.slide_count
                doc.metadata_ = metadata or doc.metadata_
                db.commit()
                db.refresh(doc)
                return doc

            new_doc = DocumentMetadata(
                id=str(uuid.uuid4()),
                document_id=document_id,
                document_name=document_name,
                file_name=file_name,
                file_type=file_type,
                version=version,
                source=source,
                chunk_count=chunk_count,
                page_count=page_count,
                slide_count=slide_count,
                metadata_=metadata
            )
            db.add(new_doc)
            db.commit()
            db.refresh(new_doc)
            return new_doc
        except Exception as e:
            db.rollback()
            logfire.error(f"Error upserting document metadata: {e}")
            raise

    @staticmethod
    def get_document_metadata(
        db: Session,
        document_id: str
    ) -> Optional[DocumentMetadata]:
        return db.query(DocumentMetadata).filter(DocumentMetadata.document_id == document_id).first()


db_service = DatabasePersistenceService()
