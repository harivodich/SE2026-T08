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

/** Bounded cleanup of aged files left by a rolled-back upload. */
@Component
public class StorageReconciler {
  private static final Logger log = LoggerFactory.getLogger(StorageReconciler.class);
  private final PrivateStorage storage;
  private final Store store;
  private final TransactionTemplate transaction;
  private final AuthService auth;
  private String lastScanned;

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
    try (var files = Files.list(storage.root())) {
      Comparator<Path> byName = Comparator.comparing(path -> path.getFileName().toString());
      PriorityQueue<Path> smallest = new PriorityQueue<>(500, byName.reversed());
      files.filter(path -> Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS))
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
}
