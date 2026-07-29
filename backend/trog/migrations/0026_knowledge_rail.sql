CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS knowledge_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key text NOT NULL UNIQUE,
    title text NOT NULL,
    source_uri text NOT NULL,
    source_type text NOT NULL,
    capability_key text,
    community_id uuid REFERENCES communities(id) ON DELETE CASCADE,
    approved boolean NOT NULL DEFAULT false,
    content_sha256 text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(source_key) BETWEEN 1 AND 160),
    CHECK (length(title) BETWEEN 1 AND 240),
    CHECK (length(source_uri) BETWEEN 1 AND 2000)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_sources_approved_scope
    ON knowledge_sources (approved, community_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_capability
    ON knowledge_sources (capability_key)
    WHERE approved;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    heading text NOT NULL,
    anchor text NOT NULL,
    content text NOT NULL,
    token_count integer NOT NULL CHECK (token_count > 0),
    embedding vector(384) NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(heading, '') || ' ' || coalesce(content, ''))
    ) STORED,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source_id
    ON knowledge_chunks (source_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_search_vector
    ON knowledge_chunks USING gin (search_vector);

COMMENT ON TABLE knowledge_sources IS
    'Approved, auditable sources available to the read-only TWE knowledge rail.';
COMMENT ON COLUMN knowledge_sources.community_id IS
    'NULL means globally approved; otherwise retrieval requires membership in this Community.';
COMMENT ON TABLE knowledge_chunks IS
    'Citation-preserving chunks with local deterministic embeddings for hybrid retrieval.';
