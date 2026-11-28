-- Persist request identity and the original response in the same
-- transaction as a review mutation. A lost HTTP response can then be replayed.
CREATE TABLE review_mutation_receipts (
    id varchar(36) PRIMARY KEY,
    owner_id varchar(36) NOT NULL REFERENCES app_users(id),
    document_id varchar(36) NOT NULL REFERENCES documents(id),
    operation varchar(20) NOT NULL,
    request_key varchar(100) NOT NULL,
    request_hash varchar(64) NOT NULL,
    response_json text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT uq_review_mutation_key UNIQUE (owner_id, operation, request_key)
);
