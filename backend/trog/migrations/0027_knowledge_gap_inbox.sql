CREATE TABLE knowledge_gaps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    signature text NOT NULL UNIQUE,
    sanitized_question text NOT NULL,
    normalized_question text NOT NULL,
    game_type text,
    intent text,
    gap_type text NOT NULL CHECK (gap_type IN ('knowledge', 'playbook', 'capability')),
    response_code text,
    safe_context jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'resolved', 'ignored')),
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    resolution_notes text,
    linked_playbook text
);

CREATE INDEX knowledge_gaps_status_last_seen_idx
    ON knowledge_gaps (status, last_seen_at DESC);
