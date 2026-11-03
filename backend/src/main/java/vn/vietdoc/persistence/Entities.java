package vn.vietdoc.persistence;

import jakarta.persistence.*;
import java.time.Instant;

public final class Entities {
  private Entities() {}

  @Entity(name = "UserAccount")
  @Table(name = "app_users")
  public static class UserAccount {
    @Id public String id;
    public String username;

    @Column(name = "password_hash")
    public String passwordHash;

    @Column(name = "created_at")
    public Instant createdAt;
  }

  @Entity(name = "Session")
  @Table(name = "sessions")
  public static class Session {
    @Id
    @Column(name = "token_hash")
    public String tokenHash;

    @Column(name = "user_id")
    public String userId;

    @Column(name = "expires_at")
    public Instant expiresAt;
  }

  @Entity(name = "Document")
  @Table(name = "documents")
  public static class Document {
    @Id public String id;

    @Column(name = "owner_id")
    public String ownerId;

    public String filename;

    @Column(name = "document_type")
    public String documentType;

    @Column(name = "content_type")
    public String contentType;

    @Column(name = "file_hash")
    public String fileHash;

    @Column(name = "file_bytes")
    public long fileBytes;

    @Column(name = "image_width")
    public int imageWidth;

    @Column(name = "image_height")
    public int imageHeight;

    @Column(name = "created_at")
    public Instant createdAt;

    public long version;

    @Column(name = "head_revision_id")
    public String headRevisionId;

    @Column(name = "active_job_id")
    public String activeJobId;

    @Column(name = "upload_key")
    public String uploadKey;
  }

  @Entity(name = "Job")
  @Table(name = "jobs")
  public static class Job {
    @Id public String id;

    @Column(name = "document_id")
    public String documentId;

    public String state;
    public String stage;

    @Column(name = "error_code")
    public String errorCode;

    @Column(name = "error_message")
    public String errorMessage;

    @Column(name = "created_at")
    public Instant createdAt;

    @Column(name = "updated_at")
    public Instant updatedAt;

    public Instant deadline;

    @Column(name = "lease_until")
    public Instant leaseUntil;

    @Column(name = "lease_token")
    public String leaseToken;

    public int attempts;

    @Column(name = "request_key")
    public String requestKey;

    @Column(name = "pipeline_manifest")
    public String pipelineManifest;

    public String mode;

    @Column(name = "result_run_id")
    public String resultRunId;
  }

  @Entity(name = "ExtractionRun")
  @Table(name = "extraction_runs")
  public static class ExtractionRun {
    @Id public String id;

    @Column(name = "job_id")
    public String jobId;

    @Column(name = "document_id")
    public String documentId;

    @Column(name = "result_json", columnDefinition = "text")
    public String resultJson;

    @Column(name = "created_at")
    public Instant createdAt;
  }

  @Entity(name = "Revision")
  @Table(name = "revisions")
  public static class Revision {
    @Id public String id;

    @Column(name = "document_id")
    public String documentId;

    @Column(name = "parent_id")
    public String parentId;

    @Column(name = "run_id")
    public String runId;

    @Column(name = "payload_json", columnDefinition = "text")
    public String payloadJson;

    @Column(name = "metadata_json", columnDefinition = "text")
    public String metadataJson;

    @Column(name = "issues_json", columnDefinition = "text")
    public String issuesJson;

    @Column(name = "row_ids_json", columnDefinition = "text")
    public String rowIdsJson;

    public String origin;

    @Column(name = "actor_id")
    public String actorId;

    @Column(length = 1000)
    public String reason;

    @Column(name = "created_at")
    public Instant createdAt;

    @Column(name = "approved_at")
    public Instant approvedAt;

    @Column(name = "approved_by")
    public String approvedBy;

    @Column(name = "approval_reason", length = 1000)
    public String approvalReason;

    @Column(name = "acknowledgements_json", columnDefinition = "text")
    public String acknowledgementsJson;
  }

  @Entity(name = "ExportArtifact")
  @Table(name = "export_artifacts")
  public static class ExportArtifact {
    @Id public String id;

    @Column(name = "document_id")
    public String documentId;

    @Column(name = "revision_id")
    public String revisionId;

    @Column(name = "exporter_version")
    public int exporterVersion;

    @Column(name = "body_json", columnDefinition = "text")
    public String bodyJson;

    public String sha256;

    @Column(name = "created_at")
    public Instant createdAt;
  }

  @Entity(name = "AuditEvent")
  @Table(name = "audit_events")
  public static class AuditEvent {
    @Id public String id;

    @Column(name = "document_id")
    public String documentId;

    @Column(name = "actor_id")
    public String actorId;

    public String action;

    @Column(name = "details_json", columnDefinition = "text")
    public String detailsJson;

    @Column(name = "created_at")
    public Instant createdAt;
  }
}
