-- Existing rows are validated by PostgreSQL before these constraints become active.
-- A primary key on id alone does not stop a document from pointing at another
-- document's otherwise valid run, revision, job, or export.
ALTER TABLE documents ADD CONSTRAINT ck_document_version_positive CHECK (version >= 1);
ALTER TABLE jobs ADD CONSTRAINT ck_job_attempts_nonnegative CHECK (attempts >= 0);

ALTER TABLE jobs ADD CONSTRAINT uq_job_id_document UNIQUE (id, document_id);
ALTER TABLE extraction_runs ADD CONSTRAINT uq_run_id_document UNIQUE (id, document_id);
ALTER TABLE revisions ADD CONSTRAINT uq_revision_id_document UNIQUE (id, document_id);

ALTER TABLE documents ADD CONSTRAINT fk_document_active_job_scoped
    FOREIGN KEY (active_job_id, id) REFERENCES jobs (id, document_id);
ALTER TABLE documents ADD CONSTRAINT fk_document_head_scoped
    FOREIGN KEY (head_revision_id, id) REFERENCES revisions (id, document_id);
ALTER TABLE extraction_runs ADD CONSTRAINT fk_run_job_scoped
    FOREIGN KEY (job_id, document_id) REFERENCES jobs (id, document_id);
ALTER TABLE revisions ADD CONSTRAINT fk_revision_parent_scoped
    FOREIGN KEY (parent_id, document_id) REFERENCES revisions (id, document_id);
ALTER TABLE revisions ADD CONSTRAINT fk_revision_run_scoped
    FOREIGN KEY (run_id, document_id) REFERENCES extraction_runs (id, document_id);
ALTER TABLE export_artifacts ADD CONSTRAINT fk_export_revision_scoped
    FOREIGN KEY (revision_id, document_id) REFERENCES revisions (id, document_id);
