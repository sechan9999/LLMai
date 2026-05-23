"""
Create the Atlas Vector Search indexes for the llmai memory store.

Usage:
  export LLMAI_MEMORY_URI="mongodb+srv://USER:PASS@cluster.mongodb.net/..."
  python scripts/setup_atlas_indexes.py

What it does:
  - Connects to the cluster
  - Creates collections ``sessions``, ``summaries``, ``knowledge`` if missing
  - Creates vector search indexes ``summaries_vector`` and ``knowledge_vector``
    on the ``embedding`` field (768-dim, cosine, nomic-embed-text)

Vector indexes are an Atlas-only feature — they require an M0-or-higher
Atlas cluster (not vanilla self-hosted MongoDB). If the createSearchIndex
command fails on your cluster, fall back to the Atlas UI walkthrough in
``docs/atlas-setup.md``.
"""
from __future__ import annotations

import os
import sys

try:
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure
except ImportError:
    sys.stderr.write(
        "pymongo not installed. Run: pip install -e '.[memory]'\n"
    )
    sys.exit(1)


VECTOR_INDEXES = {
    "summaries_vector": {
        "collection": "summaries",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 768,
                    "similarity": "cosine",
                },
                {"type": "filter", "path": "workspace_id"},
            ]
        },
    },
    "knowledge_vector": {
        "collection": "knowledge",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 768,
                    "similarity": "cosine",
                },
                {"type": "filter", "path": "workspace_id"},
                {"type": "filter", "path": "kind"},
            ]
        },
    },
}


def main() -> int:
    uri = os.environ.get("LLMAI_MEMORY_URI")
    if not uri:
        sys.stderr.write("LLMAI_MEMORY_URI not set.\n")
        return 1

    db_name = os.environ.get("LLMAI_MEMORY_DB", "llmai")
    client = MongoClient(uri, appname="llmai-setup")
    db = client[db_name]

    # Ensure collections exist (creating via insert+delete is the simplest
    # cross-cluster way that also works on M0 free tier).
    for name in ("sessions", "summaries", "knowledge"):
        if name not in db.list_collection_names():
            db.create_collection(name)
            print(f"  + created collection: {name}")
        else:
            print(f"  · collection exists: {name}")

    for index_name, spec in VECTOR_INDEXES.items():
        coll = db[spec["collection"]]
        try:
            existing = list(coll.list_search_indexes())
        except OperationFailure as exc:
            sys.stderr.write(
                f"  ! list_search_indexes failed on {spec['collection']}: {exc}\n"
                f"    Vector Search requires Atlas. Self-hosted MongoDB won't work.\n"
            )
            return 2

        names = {idx.get("name") for idx in existing}
        if index_name in names:
            print(f"  · vector index exists: {index_name}")
            continue
        try:
            coll.create_search_index({
                "name": index_name,
                "type": "vectorSearch",
                "definition": spec["definition"],
            })
            print(f"  + created vector index: {index_name} on {spec['collection']}")
        except OperationFailure as exc:
            sys.stderr.write(
                f"  ! create_search_index failed for {index_name}: {exc}\n"
            )
            return 2

    print("\nDone. Atlas may take ~1-2 minutes to finish building the indexes.")
    print("Check status in Atlas UI → Database → Search → Vector Search.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
