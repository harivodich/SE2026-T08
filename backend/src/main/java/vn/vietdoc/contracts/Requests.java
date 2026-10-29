package vn.vietdoc.contracts;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.*;
import java.util.List;

public final class Requests {
  private Requests() {}

  public record Save(
      @NotBlank String baseRevisionId,
      @Min(1) long expectedDocumentVersion,
      @NotNull JsonNode payload,
      @NotBlank @Size(max = 1000) String reason,
      @NotNull @Size(max = 30) List<String> rowIds,
      @NotNull @Size(max = 200) List<String> reviewedPaths) {}

  public record Adopt(
      @NotBlank String runId,
      @NotBlank String baseRevisionId,
      @Min(1) long expectedDocumentVersion,
      @NotBlank @Size(max = 1000) String reason) {}

  public record Approve(
      @NotBlank String revisionId,
      @Min(1) long expectedDocumentVersion,
      boolean confirmedReview,
      @NotNull @Size(max = 200) List<String> acknowledgedIssueIds,
      @NotBlank @Size(max = 1000) String reason) {}

  public record Export(
      @NotBlank String revisionId, @Pattern(regexp = "json") @NotNull String format) {}

  public record Cancel(@NotBlank String expectedState) {}
}
