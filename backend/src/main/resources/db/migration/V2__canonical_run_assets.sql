ALTER TABLE extraction_runs ADD COLUMN canonical_key varchar(250);
ALTER TABLE extraction_runs ADD COLUMN canonical_hash varchar(64);
ALTER TABLE extraction_runs ADD COLUMN canonical_width integer;
ALTER TABLE extraction_runs ADD COLUMN canonical_height integer;
ALTER TABLE jobs ADD COLUMN attempt_id varchar(36);
ALTER TABLE jobs ADD COLUMN next_attempt_at timestamp with time zone;
CREATE INDEX ix_jobs_due ON jobs(state, next_attempt_at, created_at);
