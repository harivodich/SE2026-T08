package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import jakarta.persistence.EntityManager;
import java.nio.file.*;
import java.nio.file.attribute.FileTime;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import vn.vietdoc.auth.AuthService;
import vn.vietdoc.document.*;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.Document;

class StorageReconcilerTest {
  @TempDir Path root;

  @Test
  void reachesAgedOrphanAfterFiveHundredCommittedDirectories() throws Exception {
    String orphan = "ffffffff-ffff-ffff-ffff-ffffffffffff";
    for (int i = 0; i < 500; i++) {
      String id = String.format("%08x-0000-4000-8000-000000000001", i);
      Files.createDirectory(root.resolve(id));
      Files.setLastModifiedTime(root.resolve(id), FileTime.from(Instant.now().minusSeconds(172800)));
    }
    Files.createDirectory(root.resolve(orphan));
    Files.setLastModifiedTime(root.resolve(orphan), FileTime.from(Instant.now().minusSeconds(172800)));
    Store store = mock(Store.class);
    EntityManager em = mock(EntityManager.class);
    when(store.em()).thenReturn(em);
    when(em.find(eq(Document.class), anyString())).thenAnswer(call ->
        orphan.equals(call.getArgument(1)) ? null : new Document());
    PlatformTransactionManager manager = mock(PlatformTransactionManager.class);
    when(manager.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
    var reconciler = new StorageReconciler(
        new PrivateStorage(root.toString(), 20000000), store, manager, mock(AuthService.class));
    reconciler.cleanup();
    assertTrue(Files.exists(root.resolve(orphan)));
    reconciler.cleanup();
    assertFalse(Files.exists(root.resolve(orphan)));
    assertTrue(Files.exists(root.resolve("00000000-0000-4000-8000-000000000001")));
  }
}
