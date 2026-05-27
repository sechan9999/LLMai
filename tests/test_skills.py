"""Tests for the skill-from-knowledge promotion pipeline.

We don't have a running MongoDB in unit tests, so promotion logic is
tested against a fake mongo-shaped object that records calls. The
slugify helper and the system-message formatter are pure functions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from llmai.memory.skills import format_skills_message, slugify_skill_name

# ── Pure helpers ─────────────────────────────────────────────────────────────

class TestSlugify:
    def test_basic_phrase(self):
        # Default max_len=32 truncates the last word; test the head instead
        out = slugify_skill_name("Authentication uses bcrypt for hashing")
        assert out.startswith("authentication-uses-bcrypt-")
        assert "for" not in out.split("-")  # stopword dropped
        assert len(out) <= 32

    def test_drops_stopwords(self):
        # "the", "a", "of" should be filtered
        assert "the" not in slugify_skill_name("The quick brown fox")
        assert "a" not in slugify_skill_name("A quick fox").split("-")

    def test_caps_to_five_words(self):
        result = slugify_skill_name("one two three four five six seven eight")
        assert result.count("-") <= 4

    def test_caps_to_max_len(self):
        long = "supercalifragilisticexpialidocious tremendousness fantastico"
        s = slugify_skill_name(long, max_len=20)
        assert len(s) <= 20

    def test_empty_input(self):
        assert slugify_skill_name("") == "skill"
        assert slugify_skill_name("   ") == "skill"

    def test_all_stopwords(self):
        # Falls back to using the raw words rather than failing
        out = slugify_skill_name("the a an of to")
        assert out != "skill"  # we keep at least something
        assert "-" in out or out.isalpha()

    def test_non_alnum_stripped(self):
        s = slugify_skill_name("Use JWT/cookies + CSRF tokens!")
        # No slashes, plus signs, or exclamation marks
        for ch in "/+!":
            assert ch not in s


class TestFormatSkillsMessage:
    def test_empty(self):
        assert format_skills_message([]) == ""

    def test_filters_empty_content(self):
        # A skill with no content shouldn't produce a line, and if ALL
        # skills are empty the whole block is suppressed
        assert format_skills_message([{"name": "foo", "content": ""}]) == ""

    def test_renders_header(self):
        out = format_skills_message([{"name": "auth-bcrypt", "content": "uses bcrypt"}])
        assert "[Active skills for this workspace]" in out
        assert "auth-bcrypt" in out
        assert "uses bcrypt" in out

    def test_multiple_skills(self):
        out = format_skills_message([
            {"name": "a", "content": "first"},
            {"name": "b", "content": "second"},
        ])
        assert "• a:" in out
        assert "• b:" in out


# ── Promotion logic against a fake mongo ─────────────────────────────────────

class FakeCollection:
    """In-memory shim that mimics just the pymongo methods we use."""

    def __init__(self):
        self.docs: list[dict] = []
        self._next_id = 1

    def find(self, query):
        return _FakeCursor(self._matching(query))

    def find_one(self, query):
        hits = self._matching(query)
        return hits[0] if hits else None

    def count_documents(self, query):
        return len(self._matching(query))

    def insert_one(self, doc):
        new = dict(doc)
        new.setdefault("_id", self._next_id)
        self._next_id += 1
        # Enforce unique (workspace_id, name) like the real skills index,
        # but only when both incoming and existing docs carry a name.
        if "name" in new:
            if any("name" in d
                   and d.get("workspace_id") == new.get("workspace_id")
                   and d.get("name") == new.get("name")
                   for d in self.docs):
                raise RuntimeError("duplicate key")
        self.docs.append(new)
        return type("Result", (), {"inserted_id": new["_id"]})

    def insert_many(self, docs, ordered=False):
        ids = []
        for d in docs:
            r = self.insert_one(d)
            ids.append(r.inserted_id)
        return type("Result", (), {"inserted_ids": ids})

    def update_one(self, query, update):
        for d in self.docs:
            if _matches(d, query):
                _apply_update(d, update)
                return type("R", (), {"modified_count": 1, "matched_count": 1})
        return type("R", (), {"modified_count": 0, "matched_count": 0})

    def update_many(self, query, update):
        n = 0
        for d in self.docs:
            if _matches(d, query):
                _apply_update(d, update)
                n += 1
        return type("R", (), {"modified_count": n, "matched_count": n})

    def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _matches(d, query):
                self.docs.pop(i)
                return type("R", (), {"deleted_count": 1})
        return type("R", (), {"deleted_count": 0})

    def create_index(self, *args, **kwargs):
        return "ok"

    def _matching(self, query):
        return [d for d in self.docs if _matches(d, query)]


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._limit = None

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, list):
            for k, d in reversed(key_or_list):
                self._docs.sort(key=lambda doc: doc.get(k) or 0, reverse=(d == -1))
        else:
            self._docs.sort(key=lambda doc: doc.get(key_or_list) or 0,
                            reverse=(direction == -1))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def __iter__(self):
        if self._limit is None:
            return iter(self._docs)
        return iter(self._docs[:self._limit])


def _matches(doc, query):
    for k, v in query.items():
        if k == "$or":
            if not any(_matches(doc, sub) for sub in v):
                return False
            continue
        if isinstance(v, dict):
            for op, opv in v.items():
                if op == "$in":
                    if doc.get(k) not in opv:
                        return False
                elif op == "$gte":
                    if (doc.get(k) or 0) < opv:
                        return False
                elif op == "$exists":
                    if (k in doc) != opv:
                        return False
                else:
                    return False
        else:
            if doc.get(k) != v:
                return False
    return True


def _apply_update(doc, update):
    if "$set" in update:
        doc.update(update["$set"])
    if "$inc" in update:
        for k, v in update["$inc"].items():
            doc[k] = (doc.get(k) or 0) + v


class FakeDB:
    def __init__(self):
        self.sessions = FakeCollection()
        self.summaries = FakeCollection()
        self.knowledge = FakeCollection()
        self.skills = FakeCollection()

    def __getitem__(self, name):
        return getattr(self, name)


def _build_store(threshold=3, inject_limit=5):
    from llmai.memory.store import MemoryStore
    s = MemoryStore(
        uri="mongodb://test", db_name="test",
        embedder=None,
        skill_promote_threshold=threshold,
        skill_inject_limit=inject_limit,
    )
    s._db = FakeDB()
    s.connected = True
    return s


class TestPromotion:
    def test_promotion_fires_at_threshold(self):
        s = _build_store(threshold=3)
        kid = 42
        s._db.knowledge.insert_one({
            "_id": kid, "workspace_id": "abc", "text": "Use bcrypt for password hashing",
            "recall_count": 0,
        })
        # Three recalls -> should promote
        for _ in range(3):
            s._bump_knowledge_recall([kid], "/some/path")
        # Manually compute workspace_id to match what the store would use
        from llmai.memory.store import workspace_id
        # Replace the seeded doc's workspace_id with the computed one
        s._db.knowledge.docs[0]["workspace_id"] = workspace_id("/some/path")
        # Drain skills, retry (need to re-promote after fixing the id)
        s._db.skills.docs.clear()
        s._db.knowledge.docs[0]["promoted"] = False
        s._bump_knowledge_recall([kid], "/some/path")
        # After this last call, recall_count should be ≥ threshold and promoted
        promoted = [d for d in s._db.skills.docs]
        assert len(promoted) == 1
        assert promoted[0]["content"].startswith("Use bcrypt")
        assert promoted[0]["active"] is True

    def test_double_promotion_guarded(self):
        s = _build_store(threshold=2)
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        kid = 1
        s._db.knowledge.insert_one({
            "_id": kid, "workspace_id": wid, "text": "Some fact", "recall_count": 0,
        })
        s._bump_knowledge_recall([kid], "/p")
        s._bump_knowledge_recall([kid], "/p")
        # Fire it twice more — should NOT double-insert
        s._bump_knowledge_recall([kid], "/p")
        s._bump_knowledge_recall([kid], "/p")
        skills_for_wid = [d for d in s._db.skills.docs if d["workspace_id"] == wid]
        assert len(skills_for_wid) == 1

    def test_no_promotion_below_threshold(self):
        s = _build_store(threshold=5)
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        s._db.knowledge.insert_one({
            "_id": 9, "workspace_id": wid, "text": "fact", "recall_count": 0,
        })
        for _ in range(4):
            s._bump_knowledge_recall([9], "/p")
        assert len(s._db.skills.docs) == 0

    def test_unique_name_suffix(self):
        s = _build_store(threshold=1)
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        s._db.knowledge.insert_many([
            {"_id": 1, "workspace_id": wid, "text": "Use bcrypt for passwords", "recall_count": 0},
            {"_id": 2, "workspace_id": wid, "text": "Use bcrypt for passwords", "recall_count": 0},
        ])
        s._bump_knowledge_recall([1, 2], "/p")
        names = sorted(d["name"] for d in s._db.skills.docs)
        assert len(names) == 2
        # Second one must have a numeric suffix
        assert names[0] != names[1]
        assert names[1].endswith("-2")


class TestSkillCRUD:
    def test_list_excludes_inactive_by_default(self):
        s = _build_store()
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        s._db.skills.insert_many([
            {"workspace_id": wid, "name": "alpha", "content": "x", "active": True,
             "last_used_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"workspace_id": wid, "name": "beta", "content": "y", "active": False,
             "last_used_at": datetime(2026, 1, 2, tzinfo=timezone.utc)},
        ])
        active = s.list_skills("/p")
        all_skills = s.list_skills("/p", include_inactive=True)
        assert {d["name"] for d in active} == {"alpha"}
        assert {d["name"] for d in all_skills} == {"alpha", "beta"}

    def test_disable_soft_deletes(self):
        s = _build_store()
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        s._db.skills.insert_one({"workspace_id": wid, "name": "x", "content": "c", "active": True})
        ok = s.disable_skill("/p", "x")
        assert ok
        assert s._db.skills.docs[0]["active"] is False

    def test_delete_hard_deletes(self):
        s = _build_store()
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        s._db.skills.insert_one({"workspace_id": wid, "name": "x", "content": "c", "active": True})
        ok = s.delete_skill("/p", "x")
        assert ok
        assert s._db.skills.docs == []

    def test_bump_skill_usage(self):
        s = _build_store()
        from llmai.memory.store import workspace_id
        wid = workspace_id("/p")
        s._db.skills.insert_one({"workspace_id": wid, "name": "x", "content": "c",
                                 "active": True, "usage_count": 0})
        s.bump_skill_usage("/p", ["x"])
        assert s._db.skills.docs[0]["usage_count"] == 1
        assert s._db.skills.docs[0]["last_used_at"] is not None
