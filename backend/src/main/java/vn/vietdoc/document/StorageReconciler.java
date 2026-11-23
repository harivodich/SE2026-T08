package vn.vietdoc.document;

import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.slf4j.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.Document;
import vn.vietdoc.persistence.Entities.ExtractionRun;

/** Bounded cleanup of aged files left by a rolled-back upload. */
@Component
public class StorageReconciler {
  public record OrphanPromotion(String runId, boolean hasManifest) {}
  private static final Logger log = LoggerFactory.getLogger(StorageReconciler.class);
  private final PrivateStorage storage;
  private final Store store;
  private final TransactionTemplate transaction;
  private final AuthService auth;
  private String lastScanned;
  private String lastPromotedScanned;

  public StorageReconciler(
      PrivateStorage storage, Store store, PlatformTransactionManager manager, AuthService auth) {
    this.storage = storage;
    this.store = store;
    this.transaction = new TransactionTemplate(manager);
    this.auth = auth;
  }

  @Scheduled(fixedDelay = 3600000, initialDelay = 3600000)
  public void cleanup() {
    auth.cleanup();
    List<OrphanPromotion> orphans = orphanPromotions(500, Duration.ofDays(1));
    if (!orphans.isEmpty()) log.warn("promotion_orphans count={} dry_run=true run_ids={}",
        orphans.size(), orphans.stream().limit(10).map(OrphanPromotion::runId).toList());
    try (var files = Files.list(storage.root())) {
      Comparator<Path> byName = Comparator.comparing(path -> path.getFileName().toString());
      PriorityQueue<Path> smallest = new PriorityQueue<>(500, byName.reversed());
      files.filter(path -> Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS))
          .filter(path -> canonicalUuid(path.getFileName().toString()))
          .filter(path -> lastScanned == null || path.getFileName().toString().compareTo(lastScanned) > 0)
          .forEach(path -> {
            if (smallest.size() < 500) smallest.add(path);
            else if (byName.compare(path, smallest.peek()) < 0) {
              smallest.remove();
              smallest.add(path);
            }
          });
      var batch = new ArrayList<>(smallest);
      batch.sort(byName);
      if (batch.isEmpty()) {
        lastScanned = null;
        return;
      }
      for (Path path : batch) {
        lastScanned = path.getFileName().toString();
      }
      batch.forEach(
              path -> {
                try {
                  String id = path.getFileName().toString();
                  java.util.UUID.fromString(id);
                  if (Files.getLastModifiedTime(path)
                      .toInstant()
                      .isAfter(Instant.now().minus(Duration.ofDays(1)))) return;
                  Boolean exists =
                      transaction.execute(s -> store.em().find(Document.class, id) != null);
                  if (Boolean.FALSE.equals(exists)) storage.remove(id);
                } catch (Exception e) {
                  log.warn("storage_cleanup error_type={}", e.getClass().getSimpleName());
                }
              });
    } catch (Exception e) {
      log.warn("storage_cleanup error_type={}", e.getClass().getSimpleName());
    }
  }

  /** Bounded dry-run inventory; deletion needs a separate owner-reviewed policy. */
  public List<OrphanPromotion> orphanPromotions(int limit, Duration olderThan) {
    Path promoted = storage.root().resolve("promoted");
    if (Files.isSymbolicLink(promoted) || !Files.isDirectory(promoted, LinkOption.NOFOLLOW_LINKS))
      return List.of();
    List<OrphanPromotion> report = new ArrayList<>();
    try (var entries = Files.list(promoted)) {
      List<Path> batch = entries.filter(p -> Files.isDirectory(p, LinkOption.NOFOLLOW_LINKS))
          .filter(p -> canonicalUuid(p.getFileName().toString()))
          .filter(p -> lastPromotedScanned == null ||
              p.getFileName().toString().compareTo(lastPromotedScanned) > 0)
          .sorted().limit(Math.max(0, Math.min(limit, 500))).toList();
      if (batch.isEmpty()) lastPromotedScanned = null;
      for (Path path : batch) {
        lastPromotedScanned = path.getFileName().toString();
        if (Files.getLastModifiedTime(path).toInstant().isAfter(Instant.now().minus(olderThan)))
          continue;
        String runId = path.getFileName().toString();
        Boolean referenced = transaction.execute(s -> store.em().find(ExtractionRun.class, runId) != null);
        if (Boolean.FALSE.equals(referenced))
          report.add(new OrphanPromotion(runId,
              Files.isRegularFile(path.resolve("promotion.properties"), LinkOption.NOFOLLOW_LINKS)));
      }
    } catch (Exception e) {
      log.warn("promotion_inventory error_type={}", e.getClass().getSimpleName());
    }
    return report;
  }

  private boolean canonicalUuid(String value) {
    try { return UUID.fromString(value).toString().equals(value); }
    catch (IllegalArgumentException e) { return false; }
  }
}
