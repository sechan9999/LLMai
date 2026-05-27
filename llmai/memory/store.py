"""
MongoDB Atlas-backed memory store.

Three collections:
  - sessions:   one doc per conversation (raw transcript)
  - summaries:  vector-embedded context summaries
  - knowledge:  vector-embedded per-workspace facts/decisions

All public methods are best-effort: Atlas failures are logged and
swallowed so the agent loop never crashes because the database is down.

Per-workspace scoping uses ``sha256(absolute_workspace_path)[:16]`` so
renaming a parent directory doesn't lose memory as long as the resolved
path matches.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .embeddings import Embedder

logger = logging.getLogger(__name__)


def _truthy(s: Optional[str]) -> bool:
    return (s or "").strip().lower() in ("1", "true", "yes", "on")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def workspace_id(path: str | os.PathLike) -> str:
    """Stable per-workspace identifier derived from the absolute path."""
    abs_path = str(Path(path).resolve())
    return hashlib.sha256(abs_path.encode("utf-8")).hexdigest()[:16]


def new_session_id() -> str:
    return uuid.uuid4().hex


class MemoryStore:
    """Handle for the MongoDB Atlas memory backend."""

    def __init__(
        self,
        uri: str,
        db_name: str,
        embedder: Optional[Embedder] = None,
        *,
        recall_limit: int = 3,
        connect_timeout_ms: int = 5_000,
        skill_promote_threshold: int = 3,
        skill_inject_limit: int = 5,
    ):
        self.uri = uri
        self.db_name = db_name
        self.embedder = embedder
        self.recall_limit = recall_limit
        self.connect_timeout_ms = connect_timeout_ms
        self.skill_promote_threshold = max(1, int(skill_promote_threshold))
        self.skill_inject_limit = max(0, int(skill_inject_limit))
        self._client = None
        self._db = None
        self.connected = False

    # ── Init ─────────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, cfg: dict) -> Optional["MemoryStore"]:
        """Build a store from config + env vars. Returns None when disabled."""
        enabled = _truthy(os.environ.get("LLMAI_MEMORY_ENABLED")) or bool(
            cfg.get("enabled")
        )
        if not enabled:
            return None
        uri = os.environ.get("LLMAI_MEMORY_URI") or cfg.get("uri")
        if not uri:
            logger.warning(
                "Memory enabled but no URI configured "
                "(set LLMAI_MEMORY_URI or memory.uri in config.json)."
            )
            return None
        db_name = os.environ.get("LLMAI_MEMORY_DB") or cfg.get("db_name") or "llmai"
        embed_model = (
            os.environ.get("LLMAI_MEMORY_EMBED_MODEL")
            or cfg.get("embed_model")
            or "nomic-embed-text"
        )
        embed_base = os.environ.get("OLLAMA_URL") or cfg.get("embed_url") or "http://localhost:11434"
        embedder = Embedder(base_url=embed_base, model=embed_model)
        promote_threshold = int(
            os.environ.get("LLMAI_SKILL_PROMOTE_THRESHOLD")
            or cfg.get("skill_promote_threshold")
            or 3
        )
        inject_limit = int(
            os.environ.get("LLMAI_SKILL_INJECT_LIMIT")
            or cfg.get("skill_inject_limit")
            or 5
        )
        return cls(
            uri=uri,
            db_name=db_name,
            embedder=embedder,
            recall_limit=int(cfg.get("recall_limit") or 3),
            skill_promote_threshold=promote_threshold,
            skill_inject_limit=inject_limit,
        )

    def connect(self) -> bool:
        """Open the connection. Returns True on success."""
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.warning(
                "Memory enabled but pymongo not installed; "
                "run: pip install -e '.[memory]'"
            )
            return False
        try:
            self._client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.connect_timeout_ms,
                appname="llmai",
            )
            # Force a round trip to validate connectivity
            self._client.admin.command("ping")
            self._db = self._client[self.db_name]
            self.connected = True
            self._ensure_indexes()
            logger.info("Memory store connected: db=%s", self.db_name)
            return True
        except Exception as exc:
            logger.warning("Memory store connect failed: %s", exc)
            self.connected = False
            return False

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self.connected = False

    # ── Indexes (non-vector; vector indices must be created via Atlas UI) ────

    def _ensure_indexes(self) -> None:
        try:
            self._db.sessions.create_index(
                [("workspace_id", 1), ("created_at", -1)],
                background=True,
            )
            self._db.sessions.create_index("session_id", unique=True, background=True)
            self._db.summaries.create_index(
                [("workspace_id", 1), ("created_at", -1)], background=True,
            )
            self._db.knowledge.create_index(
                [("workspace_id", 1), ("created_at", -1)], background=True,
            )
            self._db.skills.create_index(
                [("workspace_id", 1), ("active", 1), ("last_used_at", -1)],
                background=True,
            )
            # Prevent name collisions per workspace
            self._db.skills.create_index(
                [("workspace_id", 1), ("name", 1)],
                unique=True, background=True,
            )
        except Exception as exc:
            logger.warning("Index creation skipped: %s", exc)

    # ── Sessions ─────────────────────────────────────────────────────────────

    def save_session(
        self,
        *,
        session_id: str,
        workspace_path: str,
        provider: str,
        model: str,
        messages: list[dict],
        token_estimate: int,
        turn_count: int,
        ended: bool = False,
    ) -> None:
        """Upsert the session document. Best-effort."""
        if not self.connected:
            return
        try:
            now = _utcnow()
            doc: dict[str, Any] = {
                "$set": {
                    "workspace_id": workspace_id(workspace_path),
                    "workspace_path": str(workspace_path),
                    "provider": provider,
                    "model": model,
                    "messages": messages,
                    "token_estimate": token_estimate,
                    "turn_count": turn_count,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "session_id": session_id,
                    "created_at": now,
                },
            }
            if ended:
                doc["$set"]["ended_at"] = now
            self._db.sessions.update_one(
                {"session_id": session_id}, doc, upsert=True,
            )
        except Exception as exc:
            logger.warning("save_session failed: %s", exc)

    def load_session(self, session_id: str) -> Optional[dict]:
        if not self.connected:
            return None
        try:
            return self._db.sessions.find_one({"session_id": session_id})
        except Exception as exc:
            logger.warning("load_session failed: %s", exc)
            return None

    # ── Summaries ────────────────────────────────────────────────────────────

    def save_summary(
        self,
        *,
        session_id: str,
        workspace_path: str,
        summary: str,
        source_token_count: int,
    ) -> None:
        if not self.connected or not summary.strip():
            return
        try:
            embedding = self.embedder.embed(summary) if self.embedder else None
            self._db.summaries.insert_one({
                "session_id": session_id,
                "workspace_id": workspace_id(workspace_path),
                "workspace_path": str(workspace_path),
                "summary": summary,
                "embedding": embedding,
                "source_token_count": source_token_count,
                "created_at": _utcnow(),
            })
        except Exception as exc:
            logger.warning("save_summary failed: %s", exc)

    def recent_summaries(
        self, workspace_path: str, limit: Optional[int] = None,
    ) -> list[dict]:
        """Most-recent summaries for this workspace (no vector search)."""
        if not self.connected:
            return []
        try:
            cursor = (
                self._db.summaries
                .find({"workspace_id": workspace_id(workspace_path)})
                .sort("created_at", -1)
                .limit(limit or self.recall_limit)
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("recent_summaries failed: %s", exc)
            return []

    # ── Knowledge ────────────────────────────────────────────────────────────

    def save_knowledge(
        self,
        *,
        workspace_path: str,
        source_session_id: str,
        items: list[dict],
    ) -> int:
        """Insert extracted knowledge items. Returns count inserted."""
        if not self.connected or not items:
            return 0
        try:
            now = _utcnow()
            wid = workspace_id(workspace_path)
            docs: list[dict[str, Any]] = []
            for item in items:
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                docs.append({
                    "workspace_id": wid,
                    "workspace_path": str(workspace_path),
                    "source_session_id": source_session_id,
                    "kind": item.get("kind") or "fact",
                    "text": text[:1000],
                    "embedding": self.embedder.embed(text) if self.embedder else None,
                    "metadata": item.get("metadata") or {},
                    "created_at": now,
                })
            if not docs:
                return 0
            result = self._db.knowledge.insert_many(docs, ordered=False)
            return len(result.inserted_ids)
        except Exception as exc:
            logger.warning("save_knowledge failed: %s", exc)
            return 0

    # ── Recall (vector search + lexical fallback) ────────────────────────────

    def recall(
        self,
        *,
        query: str,
        workspace_path: str,
        scope: str = "both",   # summaries | knowledge | both
        limit: int = 5,
    ) -> list[dict]:
        """Semantic search over summaries and/or knowledge.

        Tries Atlas Vector Search first; falls back to a lexical recent-docs
        scan when vector indices aren't configured or embeddings unavailable.

        Side-effect: each knowledge hit's ``recall_count`` is incremented,
        and any hit that crosses ``skill_promote_threshold`` is promoted
        into the ``skills`` collection.
        """
        if not self.connected:
            return []
        embedding = self.embedder.embed(query) if self.embedder else None
        scopes = {"summaries", "knowledge"} if scope == "both" else {scope}
        results: list[dict] = []
        knowledge_hit_ids: list[Any] = []
        for coll_name in scopes:
            coll = self._db[coll_name]
            text_field = "summary" if coll_name == "summaries" else "text"
            hits = self._vector_or_lexical(
                coll, coll_name, embedding, query, workspace_path, text_field, limit,
            )
            for h in hits:
                results.append({
                    "scope": coll_name,
                    "text": h.get(text_field, ""),
                    "score": h.get("_score", 0.0),
                    "session_id": h.get("session_id") or h.get("source_session_id"),
                    "created_at": h.get("created_at"),
                    "kind": h.get("kind"),
                    "metadata": h.get("metadata"),
                })
                if coll_name == "knowledge" and h.get("_id") is not None:
                    knowledge_hit_ids.append(h["_id"])
        # Highest score first
        results.sort(key=lambda r: r.get("score", 0.0), reverse=True)

        # Side-effects (best-effort) — bump counts, maybe promote
        if knowledge_hit_ids:
            self._bump_knowledge_recall(knowledge_hit_ids, workspace_path)

        return results[:limit]

    def _vector_or_lexical(
        self,
        coll,
        coll_name: str,
        embedding: Optional[list[float]],
        query: str,
        workspace_path: str,
        text_field: str,
        limit: int,
    ) -> list[dict]:
        wid = workspace_id(workspace_path)
        if embedding is not None:
            try:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": f"{coll_name}_vector",
                            "path": "embedding",
                            "queryVector": embedding,
                            "numCandidates": max(50, limit * 10),
                            "limit": limit,
                            "filter": {"workspace_id": wid},
                        }
                    },
                    {
                        "$addFields": {
                            "_score": {"$meta": "vectorSearchScore"},
                        }
                    },
                ]
                return list(coll.aggregate(pipeline))
            except Exception as exc:
                logger.debug(
                    "Vector search on %s unavailable (%s); falling back to lexical",
                    coll_name, exc,
                )
        # Fallback: most-recent docs whose text contains the first query token
        token = (query.split() or [""])[0]
        try:
            cursor = (
                coll.find({
                    "workspace_id": wid,
                    text_field: {"$regex": _safe_regex(token), "$options": "i"},
                })
                .sort("created_at", -1)
                .limit(limit)
            )
            return list(cursor)
        except Exception as exc:
            logger.warning("Lexical fallback on %s failed: %s", coll_name, exc)
            return []

    # ── Skills (promoted knowledge facts) ────────────────────────────────────

    def _bump_knowledge_recall(self, ids: list, workspace_path: str) -> None:
        """Increment recall_count on each id, then promote any that crossed
        the threshold and haven't been promoted yet. Best-effort."""
        if not ids:
            return
        now = _utcnow()
        try:
            self._db.knowledge.update_many(
                {"_id": {"$in": ids}},
                {"$inc": {"recall_count": 1}, "$set": {"last_recalled_at": now}},
            )
        except Exception as exc:
            logger.debug("knowledge recall_count bump failed: %s", exc)
            return
        try:
            self._promote_eligible(ids, workspace_path)
        except Exception as exc:
            logger.debug("skill promotion check failed: %s", exc)

    def _promote_eligible(self, ids: list, workspace_path: str) -> None:
        """Find knowledge docs that just crossed the threshold and promote
        them to skills. Idempotent — already-promoted docs are skipped."""
        # Lazy import to avoid a hard dep at module load
        from .skills import slugify_skill_name

        candidates = list(self._db.knowledge.find({
            "_id": {"$in": ids},
            "recall_count": {"$gte": self.skill_promote_threshold},
            "$or": [
                {"promoted": {"$exists": False}},
                {"promoted": False},
            ],
        }))
        if not candidates:
            return
        now = _utcnow()
        wid = workspace_id(workspace_path)
        for doc in candidates:
            text = (doc.get("text") or "").strip()
            if not text:
                continue
            base_name = slugify_skill_name(text)
            name = self._unique_skill_name(wid, base_name)
            try:
                self._db.skills.insert_one({
                    "workspace_id": wid,
                    "workspace_path": str(workspace_path),
                    "name": name,
                    "content": text[:200],
                    "source_knowledge_id": doc["_id"],
                    "created_at": now,
                    "last_used_at": now,
                    "usage_count": 0,
                    "active": True,
                })
                self._db.knowledge.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"promoted": True, "promoted_at": now,
                              "promoted_skill_name": name}},
                )
                logger.info("Promoted knowledge to skill: %s", name)
            except Exception as exc:
                # Likely a duplicate-key race; move on
                logger.debug("promote_skill failed for %s: %s", base_name, exc)

    def _unique_skill_name(self, wid: str, base: str) -> str:
        """Append -2, -3, ... if the base slug already exists in this workspace."""
        name = base
        suffix = 2
        while self._db.skills.count_documents({"workspace_id": wid, "name": name}) > 0:
            name = f"{base}-{suffix}"
            suffix += 1
            if suffix > 99:
                return f"{base}-{int(_utcnow().timestamp())}"
        return name

    def list_skills(
        self, workspace_path: str, *, include_inactive: bool = False, limit: int = 0,
    ) -> list[dict]:
        """List skills for a workspace, most-recently-used first."""
        if not self.connected:
            return []
        try:
            q: dict[str, Any] = {"workspace_id": workspace_id(workspace_path)}
            if not include_inactive:
                q["active"] = True
            cursor = self._db.skills.find(q).sort("last_used_at", -1)
            if limit and limit > 0:
                cursor = cursor.limit(limit)
            return list(cursor)
        except Exception as exc:
            logger.warning("list_skills failed: %s", exc)
            return []

    def bump_skill_usage(self, workspace_path: str, names: list[str]) -> None:
        """Mark a batch of skills as just-used (called when injected)."""
        if not self.connected or not names:
            return
        try:
            self._db.skills.update_many(
                {"workspace_id": workspace_id(workspace_path),
                 "name": {"$in": names}},
                {"$inc": {"usage_count": 1}, "$set": {"last_used_at": _utcnow()}},
            )
        except Exception as exc:
            logger.debug("bump_skill_usage failed: %s", exc)

    def disable_skill(self, workspace_path: str, name: str) -> bool:
        """Soft-delete: stops injection but keeps the record."""
        if not self.connected:
            return False
        try:
            result = self._db.skills.update_one(
                {"workspace_id": workspace_id(workspace_path), "name": name},
                {"$set": {"active": False}},
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.warning("disable_skill failed: %s", exc)
            return False

    def delete_skill(self, workspace_path: str, name: str) -> bool:
        """Hard-delete a skill by name."""
        if not self.connected:
            return False
        try:
            result = self._db.skills.delete_one(
                {"workspace_id": workspace_id(workspace_path), "name": name},
            )
            return result.deleted_count > 0
        except Exception as exc:
            logger.warning("delete_skill failed: %s", exc)
            return False


def _safe_regex(s: str) -> str:
    """Escape a string for use as a literal regex pattern."""
    import re
    return re.escape(s)[:200]
