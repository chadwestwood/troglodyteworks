import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..db import execute, fetch_all, fetch_one

EMBEDDING_DIMENSIONS = 384
MAX_QUERY_LENGTH = 1000
MAX_RESULTS = 10
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class KnowledgeRailError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class KnowledgeChunk:
    heading: str
    anchor: str
    content: str
    token_count: int


def approved_sources(manifest_path: str | Path) -> list[dict]:
    manifest = Path(manifest_path).resolve()
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ValueError("The approved knowledge source manifest is unavailable or invalid.") from exc
    if payload.get("schema_version") != 1 or not isinstance(payload.get("sources"), list):
        raise ValueError("The approved knowledge source manifest has an unsupported schema.")

    root = manifest.parent
    sources = []
    seen_keys = set()
    for item in payload["sources"]:
        if not isinstance(item, dict) or not item.get("approved"):
            continue
        required = {
            "source_key",
            "title",
            "path",
            "source_uri",
            "source_type",
            "scope",
        }
        if required.difference(item):
            raise ValueError("An approved knowledge source is missing required metadata.")
        source_key = str(item["source_key"]).strip()
        if not source_key or source_key in seen_keys:
            raise ValueError("Approved knowledge source keys must be non-empty and unique.")
        source_path = (root / str(item["path"])).resolve()
        if source_path != root and root not in source_path.parents:
            raise ValueError("Approved knowledge source paths must remain inside the knowledge directory.")
        if not source_path.is_file():
            raise ValueError(f"Approved knowledge source is missing: {item['path']}")
        if item["scope"] != "global":
            raise ValueError("Manifest-managed sources currently support only the global scope.")
        sources.append({**item, "source_key": source_key, "resolved_path": source_path})
        seen_keys.add(source_key)
    return sources


def markdown_chunks(text: str, max_words: int = 320) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    heading = "Overview"
    body: list[str] = []

    def flush():
        nonlocal body
        content = "\n".join(body).strip()
        body = []
        if not content:
            return
        words = content.split()
        for offset in range(0, len(words), max_words):
            segment = " ".join(words[offset : offset + max_words]).strip()
            if not segment:
                continue
            suffix = "" if offset == 0 else f"-{offset // max_words + 1}"
            chunks.append(
                KnowledgeChunk(
                    heading=heading,
                    anchor=f"{slugify(heading)}{suffix}",
                    content=segment,
                    token_count=len(segment.split()),
                )
            )

    for line in text.splitlines():
        match = _HEADING_PATTERN.match(line)
        if match:
            flush()
            heading = match.group(2).strip()
        else:
            body.append(line)
    flush()
    return chunks


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a stable, local feature-hashing embedding without external secrets."""
    tokens = _TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return [0.0] * dimensions
    features = list(tokens)
    features.extend(f"{left}::{right}" for left, right in zip(tokens, tokens[1:]))
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def sync_approved_sources(database, manifest_path: str | Path) -> dict:
    sources = approved_sources(manifest_path)
    synced_chunks = 0
    source_keys = [source["source_key"] for source in sources]
    with database.connect() as conn:
        execute(
            conn,
            """
            UPDATE knowledge_sources
            SET approved = false, updated_at = now()
            WHERE metadata->>'managed_by' = 'approved-manifest'
              AND NOT (source_key = ANY(%s))
            """,
            (source_keys,),
        )
        for source in sources:
            content = source["resolved_path"].read_text(encoding="utf-8").strip()
            content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            metadata = {
                "managed_by": "approved-manifest",
                "path": source["path"],
                "scope": source["scope"],
            }
            row = fetch_one(
                conn,
                """
                INSERT INTO knowledge_sources
                    (source_key, title, source_uri, source_type, capability_key,
                     community_id, approved, content_sha256, metadata)
                VALUES (%s, %s, %s, %s, %s, NULL, true, %s, %s::jsonb)
                ON CONFLICT (source_key) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_uri = EXCLUDED.source_uri,
                    source_type = EXCLUDED.source_type,
                    capability_key = EXCLUDED.capability_key,
                    community_id = NULL,
                    approved = true,
                    content_sha256 = EXCLUDED.content_sha256,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                RETURNING id::text
                """,
                (
                    source["source_key"],
                    source["title"],
                    source["source_uri"],
                    source["source_type"],
                    source.get("capability_key"),
                    content_sha256,
                    json.dumps(metadata),
                ),
            )
            source_id = row["id"]
            execute(conn, "DELETE FROM knowledge_chunks WHERE source_id = %s", (source_id,))
            for chunk_index, chunk in enumerate(markdown_chunks(content)):
                chunk_metadata = {
                    "source_key": source["source_key"],
                    "capability_key": source.get("capability_key"),
                }
                execute(
                    conn,
                    """
                    INSERT INTO knowledge_chunks
                        (source_id, chunk_index, heading, anchor, content,
                         token_count, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s::jsonb)
                    """,
                    (
                        source_id,
                        chunk_index,
                        chunk.heading,
                        chunk.anchor,
                        chunk.content,
                        chunk.token_count,
                        vector_literal(embed_text(f"{source['title']} {chunk.heading} {chunk.content}")),
                        json.dumps(chunk_metadata),
                    ),
                )
                synced_chunks += 1
    return {"sources": len(sources), "chunks": synced_chunks}


class KnowledgeRail:
    def __init__(self, database):
        self.database = database

    def search(
        self,
        identity: dict,
        query: str,
        capability_key: str | None = None,
        community_id: str | None = None,
        limit: int = 5,
    ) -> dict:
        query = " ".join(str(query or "").split())
        if not query:
            raise KnowledgeRailError("INVALID_ARGUMENT", "A knowledge search query is required.")
        if len(query) > MAX_QUERY_LENGTH:
            raise KnowledgeRailError("INVALID_ARGUMENT", "The knowledge search query is too long.")
        capability_key = " ".join(str(capability_key or "").split()) or None
        limit = max(1, min(int(limit), MAX_RESULTS))
        embedded_query = embed_text(query)
        if not any(embedded_query):
            raise KnowledgeRailError(
                "INVALID_ARGUMENT",
                "The knowledge search query must contain searchable words.",
            )
        if community_id:
            try:
                community_id = str(uuid.UUID(str(community_id)))
            except (ValueError, TypeError, AttributeError):
                raise KnowledgeRailError(
                    "INVALID_ARGUMENT",
                    "The Community knowledge scope is invalid.",
                ) from None
        query_vector = vector_literal(embedded_query)

        with self.database.connect() as conn:
            if community_id and not fetch_one(
                conn,
                """
                SELECT 1
                FROM community_memberships
                WHERE community_id = %s AND user_id = %s
                """,
                (community_id, identity["user_id"]),
            ):
                # Do not reveal whether the requested Community exists.
                raise KnowledgeRailError("NOT_FOUND", "The requested knowledge scope was not found.")
            rows = fetch_all(
                conn,
                """
                WITH ranked AS (
                    SELECT ks.source_key, ks.title, ks.source_uri,
                           ks.source_type, ks.capability_key,
                           ks.community_id::text, kc.heading, kc.anchor,
                           kc.content, kc.token_count,
                           1 - (kc.embedding <=> %s::vector) AS vector_score,
                           ts_rank_cd(
                               kc.search_vector,
                               websearch_to_tsquery('english', %s)
                           ) AS text_score
                    FROM knowledge_chunks kc
                    JOIN knowledge_sources ks ON ks.id = kc.source_id
                    WHERE ks.approved
                      AND (
                          ks.community_id IS NULL
                          OR EXISTS (
                              SELECT 1
                              FROM community_memberships cm
                              WHERE cm.community_id = ks.community_id
                                AND cm.user_id = %s
                          )
                      )
                      AND (%s::text IS NULL OR ks.capability_key = %s)
                      AND (
                          %s::uuid IS NULL
                          OR ks.community_id IS NULL
                          OR ks.community_id = %s::uuid
                      )
                )
                SELECT *,
                       (0.65 * vector_score)
                       + (0.35 * LEAST(1.0, text_score * 4.0)) AS score
                FROM ranked
                ORDER BY score DESC, source_key, anchor
                LIMIT %s
                """,
                (
                    query_vector,
                    query,
                    identity["user_id"],
                    capability_key,
                    capability_key,
                    community_id,
                    community_id,
                    limit,
                ),
            )

        results = []
        for row in rows:
            citation_uri = f"{row['source_uri']}#{row['anchor']}"
            results.append(
                {
                    "content": row["content"],
                    "heading": row["heading"],
                    "score": round(float(row["score"]), 6),
                    "capability_key": row["capability_key"],
                    "scope": (
                        {"type": "community", "community_id": row["community_id"]}
                        if row["community_id"]
                        else {"type": "global"}
                    ),
                    "citation": {
                        "source_key": row["source_key"],
                        "title": row["title"],
                        "uri": citation_uri,
                        "label": f"{row['title']} — {row['heading']}",
                    },
                }
            )
        return {
            "query": query,
            "capability_key": capability_key,
            "results": results,
            "grounding": {
                "result_count": len(results),
                "instruction": (
                    "Answer only from these excerpts and cite their citation URI. "
                    "If they do not support an answer, say that approved TWE knowledge is insufficient."
                ),
            },
        }
