package vn.vietdoc.document;

import jakarta.validation.Valid;
import java.util.*;
import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import vn.vietdoc.auth.AuthService.Identity;
import vn.vietdoc.contracts.Requests;
import vn.vietdoc.export.ExportService;
import vn.vietdoc.job.JobService;
import vn.vietdoc.review.ReviewService;

@RestController
@RequestMapping("/api/v1")
public class DocumentController {
  private final DocumentService documents;
  private final JobService jobs;
  private final ReviewService review;
  private final ExportService exports;

  public DocumentController(
      DocumentService documents, JobService jobs, ReviewService review, ExportService exports) {
    this.documents = documents;
    this.jobs = jobs;
    this.review = review;
    this.exports = exports;
  }

  @PostMapping("/documents")
  @ResponseStatus(HttpStatus.CREATED)
  public DocumentService.DocumentView upload(
      @AuthenticationPrincipal Identity user,
      @RequestPart("file") MultipartFile file,
      @RequestParam("document_type") String type,
      @RequestHeader(value = "Idempotency-Key", required = false) String key) {
    return documents.upload(user.id(), file, type, key);
  }

  @GetMapping("/documents")
  public DocumentService.Page<DocumentService.DocumentView> list(
      @AuthenticationPrincipal Identity user,
      @RequestParam(required = false) String type,
      @RequestParam(required = false) String status,
      @RequestParam(required = false) String cursor,
      @RequestParam(defaultValue = "20") int limit) {
    return documents.list(user.id(), type, status, cursor, limit);
  }

  @GetMapping("/documents/{id}")
  public DocumentService.DocumentView detail(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.get(id, user.id());
  }

  @GetMapping("/documents/{id}/pages/0")
  public ResponseEntity<byte[]> page(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return ResponseEntity.ok()
        .contentType(MediaType.IMAGE_PNG)
        .cacheControl(CacheControl.noStore())
        .body(documents.page(id, user.id()));
  }

  @PostMapping("/documents/{id}/jobs")
  @ResponseStatus(HttpStatus.ACCEPTED)
  public DocumentService.JobView createJob(
      @PathVariable String id,
      @AuthenticationPrincipal Identity user,
      @RequestHeader(value = "Idempotency-Key", required = false) String key) {
    return jobs.create(id, user.id(), key);
  }

  @GetMapping("/jobs/{id}")
  public DocumentService.JobView job(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return jobs.get(id, user.id());
  }

  @PostMapping("/jobs/{id}/cancel")
  public DocumentService.JobView cancel(
      @PathVariable String id,
      @AuthenticationPrincipal Identity user,
      @Valid @RequestBody Requests.Cancel input) {
    return jobs.cancel(id, user.id(), input.expectedState());
  }

  @GetMapping("/documents/{id}/runs")
  public DocumentService.Page<DocumentService.RunView> runs(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.runs(id, user.id());
  }

  @GetMapping("/runs/{id}")
  public DocumentService.RunView run(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.run(id, user.id());
  }

  @GetMapping("/documents/{id}/revisions")
  public DocumentService.Page<DocumentService.RevisionView> revisions(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.revisions(id, user.id());
  }

  @GetMapping("/revisions/{id}")
  public DocumentService.RevisionView revision(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.revision(id, user.id());
  }

  @PatchMapping("/documents/{id}/review")
  @ResponseStatus(HttpStatus.CREATED)
  public DocumentService.DocumentView save(
      @PathVariable String id,
      @AuthenticationPrincipal Identity user,
      @Valid @RequestBody Requests.Save input) {
    return review.save(id, user.id(), input);
  }

  @PostMapping("/documents/{id}/adopt-run")
  @ResponseStatus(HttpStatus.CREATED)
  public DocumentService.DocumentView adopt(
      @PathVariable String id,
      @AuthenticationPrincipal Identity user,
      @Valid @RequestBody Requests.Adopt input) {
    return review.adopt(id, user.id(), input);
  }

  @PostMapping("/documents/{id}/approve")
  @ResponseStatus(HttpStatus.CREATED)
  public DocumentService.DocumentView approve(
      @PathVariable String id,
      @AuthenticationPrincipal Identity user,
      @Valid @RequestBody Requests.Approve input) {
    return review.approve(id, user.id(), input);
  }

  @PostMapping("/documents/{id}/exports")
  @ResponseStatus(HttpStatus.CREATED)
  public DocumentService.ExportView export(
      @PathVariable String id,
      @AuthenticationPrincipal Identity user,
      @Valid @RequestBody Requests.Export input) {
    return exports.create(id, user.id(), input);
  }

  @GetMapping("/documents/{id}/exports")
  public DocumentService.Page<DocumentService.ExportView> exports(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.exports(id, user.id());
  }

  @GetMapping("/exports/{id}/download")
  public ResponseEntity<byte[]> download(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("Content-Disposition", "attachment; filename=\"vietdoc-" + id + ".json\"")
        .cacheControl(CacheControl.noStore())
        .body(exports.download(id, user.id()));
  }

  @GetMapping("/documents/{id}/audit")
  public DocumentService.Page<DocumentService.AuditView> audit(
      @PathVariable String id, @AuthenticationPrincipal Identity user) {
    return documents.audit(id, user.id());
  }
}
