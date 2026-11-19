package lab.platform;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import reactor.core.publisher.Flux;

@SpringBootTest(
    properties = {
      "spring.datasource.url=jdbc:h2:mem:platform;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
      "spring.datasource.username=sa",
      "spring.datasource.password=",
      "platform.jwt-secret=test-only-secret-which-is-over-thirty-two-characters",
      "platform.demo=false",
      "platform.storage=target/test-storage",
      "platform.rag-root=target/test-rag"
    })
@AutoConfigureMockMvc
class PlatformTest {
  @Autowired MockMvc mvc;
  @Autowired Store store;
  @MockBean AgentClient agent;

  @BeforeEach
  void prepare() {
    when(agent.query(anyMap()))
        .thenReturn(
            Flux.just("{\"type\":\"delta\",\"text\":\"Verified answer\"}", "{\"type\":\"done\"}"));
    when(agent.ingest(anyMap())).thenReturn(Map.of("pages", 1, "chunks", 1));
  }

  String register() throws Exception {
    String json =
        store.encode(
            Map.of(
                "email",
                UUID.randomUUID() + "@example.com",
                "name",
                "Test",
                "password",
                "test-password-123"));
    var r =
        mvc.perform(
                post("/api/auth/register").contentType(MediaType.APPLICATION_JSON).content(json))
            .andExpect(status().isOk())
            .andReturn();
    return store.json.readTree(r.getResponse().getContentAsString()).get("token").asText();
  }

  String conversation(String token) throws Exception {
    var r =
        mvc.perform(post("/api/conversations").header("Authorization", "Bearer " + token))
            .andExpect(status().isOk())
            .andReturn();
    return store.json.readTree(r.getResponse().getContentAsString()).get("id").asText();
  }

  @Test
  void authenticationAndLogout() throws Exception {
    mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    String token = register();
    mvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + token))
        .andExpect(status().isOk());
    mvc.perform(post("/api/auth/logout").header("Authorization", "Bearer " + token))
        .andExpect(status().isOk());
    mvc.perform(get("/api/auth/me").header("Authorization", "Bearer " + token))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void conversationOwnershipIsEnforced() throws Exception {
    String a = register(), b = register(), id = conversation(a);
    mvc.perform(
            get("/api/conversations/" + id + "/messages").header("Authorization", "Bearer " + b))
        .andExpect(status().isNotFound());
    mvc.perform(
            patch("/api/conversations/" + id)
                .header("Authorization", "Bearer " + b)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"stolen\"}"))
        .andExpect(status().isNotFound());
  }

  @Test
  void duplicateRequestsCreateOneTaskAndConflictsAreRejected() throws Exception {
    String token = register(), id = conversation(token), key = UUID.randomUUID().toString();
    String body =
        store.encode(
            Map.of(
                "question",
                "What is revenue?",
                "mode",
                "evidence",
                "documentIds",
                List.of(),
                "idempotencyKey",
                key));
    String endpoint = "/api/conversations/" + id + "/messages";
    var first =
        mvc.perform(
                post(endpoint)
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body))
            .andExpect(status().isOk())
            .andReturn();
    String task = store.json.readTree(first.getResponse().getContentAsString()).get("id").asText();
    mvc.perform(
            post(endpoint)
                .header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(task));
    mvc.perform(
            post(endpoint)
                .header("Authorization", "Bearer " + token)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body.replace("What is revenue?", "A different question")))
        .andExpect(status().isConflict());
    for (int n = 0; n < 100; n++) {
      var r = store.one("SELECT * FROM agent_runs WHERE id=?", task);
      if (r.get("run_status").equals("SUCCEEDED")) break;
      Thread.sleep(20);
    }
    assertEquals(
        1,
        store.jdbc.queryForObject(
            "SELECT COUNT(*) FROM agent_runs WHERE conversation_id=?", Integer.class, id));
    assertEquals(
        2,
        store.jdbc.queryForObject(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=?", Integer.class, id));
    assertEquals(
        "SUCCEEDED", store.one("SELECT * FROM agent_runs WHERE id=?", task).get("run_status"));
    var events =
        mvc.perform(get("/api/runs/" + task + "/events").header("Authorization", "Bearer " + token))
            .andExpect(request().asyncStarted())
            .andReturn();
    mvc.perform(asyncDispatch(events)).andExpect(status().isOk());
  }

  @Test
  void privateDocumentCannotBeReadByAnotherUser() throws Exception {
    String a = register(), b = register();
    var file =
        new MockMultipartFile(
            "file", "notes.txt", "text/plain", "Revenue was 42 million in 2025.".getBytes());
    var res =
        mvc.perform(multipart("/api/documents").file(file).header("Authorization", "Bearer " + a))
            .andExpect(status().isOk())
            .andReturn();
    String id = store.json.readTree(res.getResponse().getContentAsString()).get("id").asText();
    mvc.perform(get("/api/documents/" + id + "/file").header("Authorization", "Bearer " + b))
        .andExpect(status().isNotFound());
    mvc.perform(get("/api/documents/" + id + "/file").header("Authorization", "Bearer " + a))
        .andExpect(status().isOk());
  }

  @Test
  void invalidPdfAndOversizedQuestionAreRejected() throws Exception {
    String t = register();
    mvc.perform(
            multipart("/api/documents")
                .file(
                    new MockMultipartFile(
                        "file", "fake.pdf", "application/pdf", "not a pdf".getBytes()))
                .header("Authorization", "Bearer " + t))
        .andExpect(status().isBadRequest());
    String c = conversation(t);
    mvc.perform(
            post("/api/conversations/" + c + "/messages")
                .header("Authorization", "Bearer " + t)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    store.encode(
                        Map.of(
                            "question",
                            "x".repeat(4001),
                            "mode",
                            "evidence",
                            "idempotencyKey",
                            "limit-test"))))
        .andExpect(status().isBadRequest());
  }

  @Test
  void cancellationHasAnExplicitPersistentState() throws Exception {
    when(agent.query(anyMap()))
        .thenReturn(
            Flux.interval(java.time.Duration.ofMillis(20))
                .map(n -> "{\"type\":\"delta\",\"text\":\"partial \"}"));
    String token = register();
    String conversationId = conversation(token);
    String body =
        store.encode(
            Map.of(
                "question",
                "Slow query",
                "mode",
                "evidence",
                "idempotencyKey",
                UUID.randomUUID().toString()));
    var response =
        mvc.perform(
                post("/api/conversations/" + conversationId + "/messages")
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body))
            .andExpect(status().isOk())
            .andReturn();
    String id = store.json.readTree(response.getResponse().getContentAsString()).get("id").asText();
    mvc.perform(post("/api/runs/" + id + "/cancel").header("Authorization", "Bearer " + token))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("CANCELLED"));
    assertEquals(
        "CANCELLED", store.one("SELECT * FROM agent_runs WHERE id=?", id).get("run_status"));
  }
}
