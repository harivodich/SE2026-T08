package vn.vietdoc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.YamlPropertiesFactoryBean;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.env.*;
import vn.vietdoc.common.Json;
import vn.vietdoc.contracts.ContractValidator;
import vn.vietdoc.document.DocumentService;
import vn.vietdoc.job.JobService;
import vn.vietdoc.persistence.Store;
import vn.vietdoc.review.ReviewService;

class DemoConfigurationTest {
  @Test
  void demoProfileReadsDocumentedAiModeAndManifestEnvironmentAliases() {
    var yaml = new YamlPropertiesFactoryBean();
    yaml.setResources(new ClassPathResource("application-demo.yml"));
    var environment = new StandardEnvironment();
    environment.getPropertySources().addFirst(new MapPropertySource("documented-env",
        Map.of("AI_MODE", "manual", "PIPELINE_MANIFEST", "release.v2")));
    environment.getPropertySources().addLast(new PropertiesPropertySource("demo", yaml.getObject()));
    assertEquals("manual", environment.getProperty("vietdoc.mode"));
    assertEquals("release.v2", environment.getProperty("vietdoc.pipeline-manifest"));
  }

  @Test
  void httpModeCannotStartBeforeComputeContractIsImplemented() {
    assertThrows(IllegalStateException.class, () -> new JobService(
        mock(Store.class), mock(Json.class), mock(ContractValidator.class),
        mock(DocumentService.class), mock(ReviewService.class),
        "http", "unapproved", 180, 30, 3));
  }
}
