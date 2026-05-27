"""
End-to-end memory tests against a real MongoDB / Atlas cluster.

Setup before running:
  export LLMAI_TEST_MONGO_URI="mongodb://localhost:27017"   # or Atlas URI
  pytest tests/integration/test_memory_e2e.py -m integration -v

These tests create + drop a uniquely-named test database so they don't
collide with a real `llmai` database that may exist on the same cluster.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


def test_connect_and_session_round_trip(mongo_uri):
    """Connect, save a session, read it back."""
    pytest.importorskip("pymongo")
    from llmai.memory.store import MemoryStore

    db_name = f"llmai_itest_{uuid.uuid4().hex[:8]}"
    store = MemoryStore(uri=mongo_uri, db_name=db_name, embedder=None)
    try:
        assert store.connect(), "could not connect to MongoDB"
        sid = "test-session-1"
        store.save_session(
            session_id=sid,
            workspace_path="/tmp/itest",
            provider="ollama",
            model="qwen2.5-coder",
            messages=[{"role": "user", "content": "hello"}],
            token_estimate=10,
            turn_count=1,
        )
        loaded = store.load_session(sid)
        assert loaded is not None
        assert loaded["session_id"] == sid
        assert loaded["turn_count"] == 1
    finally:
        try:
            store._client.drop_database(db_name)
        except Exception:
            pass
        store.close()


def test_promotion_at_threshold(mongo_uri):
    """Three recall hits on a knowledge doc → promoted to skill."""
    from llmai.memory.store import MemoryStore, workspace_id

    db_name = f"llmai_itest_{uuid.uuid4().hex[:8]}"
    store = MemoryStore(
        uri=mongo_uri, db_name=db_name, embedder=None,
        skill_promote_threshold=3,
    )
    try:
        assert store.connect()
        wid = workspace_id("/tmp/itest-promo")
        store._db.knowledge.insert_one({
            "workspace_id": wid,
            "workspace_path": "/tmp/itest-promo",
            "source_session_id": "s1",
            "kind": "fact",
            "text": "Use bcrypt for password hashing in this codebase",
            "recall_count": 0,
        })
        kid = store._db.knowledge.find_one(
            {"workspace_id": wid}
        )["_id"]
        for _ in range(3):
            store._bump_knowledge_recall([kid], "/tmp/itest-promo")
        skills = list(store._db.skills.find({"workspace_id": wid}))
        assert len(skills) == 1, f"expected 1 promoted skill, got {len(skills)}"
        assert skills[0]["content"].startswith("Use bcrypt")
    finally:
        try:
            store._client.drop_database(db_name)
        except Exception:
            pass
        store.close()
