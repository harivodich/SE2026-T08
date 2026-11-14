package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import jakarta.persistence.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import vn.vietdoc.common.*;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.*;
import vn.vietdoc.persistence.*;
import vn.vietdoc.persistence.Entities.Document;

class DocumentSearchUnitTest {
  final Store store = mock(Store.class);
  final DocumentService service = new DocumentService(store, mock(Json.class),
      mock(PrivateStorage.class), mock(ContractValidator.class), mock(PlatformTransactionManager.class));

  @Test void tc14_oversizedQueryRejectedBeforeDatabaseAccess() {
    ApiException e = assertThrows(ApiException.class,
        () -> service.list("u", null, null, null, 20, "x".repeat(129)));
    assertEquals(400, e.status); assertEquals("INVALID_QUERY", e.code);
    verifyNoInteractions(store);
  }

  @Test @SuppressWarnings("unchecked") void tc15_boundaryQueryAndEmptyResultHaveNoCursor() {
    EntityManager em = mock(EntityManager.class);
    TypedQuery<Document> query = mock(TypedQuery.class, RETURNS_SELF);
    when(store.em()).thenReturn(em);
    when(em.createQuery(anyString(), eq(Document.class))).thenReturn(query);
    when(query.getResultList()).thenReturn(List.of());
    var page = service.list("u", null, null, null, 20, "x".repeat(128));
    assertTrue(page.items().isEmpty()); assertNull(page.nextCursor());
    verify(query).setParameter("q", "%" + "x".repeat(128) + "%");
  }
}
