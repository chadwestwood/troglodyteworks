ALTER TABLE knowledge_gaps
    DROP CONSTRAINT IF EXISTS knowledge_gaps_gap_type_check;

ALTER TABLE knowledge_gaps
    ADD CONSTRAINT knowledge_gaps_gap_type_check
    CHECK (
        gap_type IN (
            'knowledge',
            'playbook',
            'capability',
            'live_data',
            'provider_outage',
            'authorization',
            'configuration',
            'validation',
            'routing',
            'internal_error',
            'rate_limit',
            'topic_boundary',
            'unknown'
        )
    );

ALTER TABLE knowledge_gaps
    ADD COLUMN IF NOT EXISTS assistant_response text;
