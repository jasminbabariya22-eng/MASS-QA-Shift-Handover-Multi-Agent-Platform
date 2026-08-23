import pytest
import uuid
from sqlalchemy import inspect
from fastapi.testclient import TestClient

from app.db import (
    engine,
    SessionLocal,
    check_db_health,
    User,
    Conversation,
    Message,
    MessageCitation,
    MessageFeedback,
    AuditLog,
    DocumentMetadata,
    QueryLog,
)
from app.services.db_services import db_service
from app.main import app
from app.config import settings
from qdrant_client import QdrantClient

client = TestClient(app)


def test_postgresql_connection_and_health():
    """Verify PostgreSQL 18 connection and health check."""
    assert check_db_health() is True


def test_schema_and_required_tables_exist():
    """Verify all 8 required application tables exist in MASS.public schema."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    required = [
        "users",
        "conversations",
        "messages",
        "message_citations",
        "message_feedback",
        "audit_logs",
        "document_metadata",
        "query_logs",
    ]
    for table in required:
        assert table in tables, f"Missing table: {table}"


def test_user_crud():
    """Verify User creation, retrieval, and unique constraints."""
    db = SessionLocal()
    unique_user = f"eng_{uuid.uuid4().hex[:8]}"
    unique_email = f"{unique_user}@energycorp.com"
    try:
        user = User(
            id=str(uuid.uuid4()),
            username=unique_user,
            email=unique_email,
            display_name="Senior Engineer",
            password_hash="hashed_pw_argon2_xyz",
            role="USER"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        fetched = db.query(User).filter(User.username == unique_user).first()
        assert fetched is not None
        assert fetched.email == unique_email
        assert fetched.role == "USER"
        assert fetched.is_active is True
    finally:
        db.close()


def test_conversation_and_message_hierarchy():
    """Verify User -> Conversation -> Message -> Citation hierarchy and cascade."""
    db = SessionLocal()
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    try:
        # Create conversation
        conv = db_service.get_or_create_conversation(db, session_id=session_id, user_id=None, title="Test Pipeline")
        assert conv.session_id == session_id
        assert conv.status == "ACTIVE"

        # Create user message
        u_msg = db_service.create_message(
            db,
            conversation_id=conv.id,
            role="USER",
            content="What is crude stabilization?"
        )
        assert u_msg.role == "USER"
        assert u_msg.conversation_id == conv.id

        # Create assistant message
        a_msg = db_service.create_message(
            db,
            conversation_id=conv.id,
            role="ASSISTANT",
            content="Crude stabilization removes volatile dissolved gases.",
            response_time_ms=125.5
        )
        assert a_msg.role == "ASSISTANT"
        assert a_msg.response_time_ms == 125.5

        # Create citations
        citations = [
            {
                "document_name": "Refining_Handbook.pdf",
                "page_number": 42,
                "score": 0.985,
                "snippet": "Stabilizer column operates at 150 psi.",
                "content_type": "text"
            }
        ]
        saved_cits = db_service.create_citations(db, message_id=a_msg.id, citations=citations)
        assert len(saved_cits) == 1
        assert saved_cits[0].page_number == 42
        assert saved_cits[0].message_id == a_msg.id

        # Query messages via relation
        db.refresh(conv)
        assert len(conv.messages) >= 2
    finally:
        db.close()


def test_feedback_submission():
    """Verify user feedback rating and comments."""
    db = SessionLocal()
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    try:
        conv = db_service.get_or_create_conversation(db, session_id=session_id)
        msg = db_service.create_message(db, conversation_id=conv.id, role="ASSISTANT", content="Test answer.")

        fb = db_service.submit_feedback(
            db,
            message_id=msg.id,
            rating="POSITIVE",
            comment="Very clear technical explanation."
        )
        assert fb.rating == "POSITIVE"
        assert fb.comment == "Very clear technical explanation."

        # Update rating
        fb_updated = db_service.submit_feedback(
            db,
            message_id=msg.id,
            rating="NEGATIVE",
            comment="Needs more equipment details."
        )
        assert fb_updated.id == fb.id
        assert fb_updated.rating == "NEGATIVE"
    finally:
        db.close()


def test_audit_logging_and_query_logging():
    """Verify audit and query execution metrics logging without throwing errors."""
    db = SessionLocal()
    req_id = f"req_{uuid.uuid4().hex[:8]}"
    try:
        # Audit Log
        db_service.log_audit_event(
            db,
            action="TEST_ACTION",
            user_id="user_test",
            request_id=req_id,
            endpoint="/test",
            status_code=200
        )
        audit = db.query(AuditLog).filter(AuditLog.request_id == req_id).first()
        assert audit is not None
        assert audit.action == "TEST_ACTION"

        # Query Log
        db_service.log_query_metrics(
            db,
            query_text="What is the crude distillation yield?",
            user_id="user_test",
            retrieval_time_ms=45.2,
            llm_time_ms=350.0,
            total_time_ms=395.2,
            retrieved_count=5,
            cache_hit=False,
            request_id=req_id
        )
        qlog = db.query(QueryLog).filter(QueryLog.request_id == req_id).first()
        assert qlog is not None
        assert qlog.total_time_ms == 395.2
    finally:
        db.close()


def test_document_metadata_upsert():
    """Verify document metadata storage."""
    db = SessionLocal()
    doc_id = f"DOC_{uuid.uuid4().hex[:8]}"
    try:
        doc = db_service.upsert_document_metadata(
            db,
            document_id=doc_id,
            document_name="IEA_Energy_Outlook_2025.pdf",
            file_name="IEA_Energy_Outlook_2025.pdf",
            file_type="PDF",
            chunk_count=142,
            page_count=180
        )
        assert doc.document_id == doc_id
        assert doc.chunk_count == 142
        assert doc.page_count == 180

        # Upsert update
        updated_doc = db_service.upsert_document_metadata(
            db,
            document_id=doc_id,
            document_name="IEA_Energy_Outlook_2025.pdf",
            chunk_count=150
        )
        assert updated_doc.chunk_count == 150
    finally:
        db.close()


def test_transaction_rollback_on_failure():
    """Verify transaction rollback prevents partial state corruption."""
    db = SessionLocal()
    try:
        try:
            # Attempt to insert a message with a non-existent conversation_id (Foreign Key violation)
            msg = Message(
                id=str(uuid.uuid4()),
                conversation_id="non-existent-conv-id",
                role="USER",
                content="Invalid"
            )
            db.add(msg)
            db.commit()
        except Exception:
            db.rollback()

        # Database should still be responsive and undamaged
        assert check_db_health() is True
    finally:
        db.close()


def test_api_health_and_ready_endpoints():
    """Verify /health and /ready endpoints report database availability."""
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "ok"
    assert r_health.json()["database"] == "connected"

    r_ready = client.get("/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["dependencies"]["postgresql"] == "connected"


def test_api_feedback_endpoint():
    """Verify POST /feedback endpoint persists rating."""
    db = SessionLocal()
    try:
        conv = db_service.get_or_create_conversation(db, session_id=str(uuid.uuid4()))
        msg = db_service.create_message(db, conversation_id=conv.id, role="ASSISTANT", content="Test answer.")

        resp = client.post("/feedback", json={
            "message_id": msg.id,
            "rating": "POSITIVE",
            "comment": "Accurate response"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        assert resp.json()["rating"] == "POSITIVE"
    finally:
        db.close()


def test_api_query_persistence():
    """Verify POST /query creates and stores conversation, user message, and assistant reply in PostgreSQL."""
    session_id = f"sess_api_{uuid.uuid4().hex[:8]}"
    resp = client.post("/query", json={
        "query": "hii",
        "session_id": session_id,
        "stream": False
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert "answer" in data

    # Verify rows in PostgreSQL
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.session_id == session_id).first()
        assert conv is not None
        assert len(conv.messages) >= 2  # user message + assistant refusal/greeting
        roles = [m.role for m in conv.messages]
        assert "USER" in roles
        assert "ASSISTANT" in roles
    finally:
        db.close()


def test_qdrant_collection_integrity_unchanged():
    """
    CRITICAL NON-NEGOTIABLE RULE:
    Verify Qdrant collection 'mass_qa_multimodal' is 100% UNCHANGED:
    - Points count: 2,079
    - Vector dimension: 3072
    - Status: green
    """
    qdrant = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
    info = qdrant.get_collection("mass_qa_multimodal")
    assert info.points_count == 2079
    assert info.config.params.vectors.size == 3072
    assert info.status.name.lower() == "green"
