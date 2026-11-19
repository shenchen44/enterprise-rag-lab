package lab.platform;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.io.*;
import java.nio.file.*;
import java.security.Principal;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api")
public class ApiController {
  final Store s;
  final PlatformService p;
  final AuthService auth;
  final AgentClient agent;
  final Path storage, rag;

  public ApiController(
      Store s,
      PlatformService p,
      AuthService auth,
      AgentClient agent,
      @Value("${platform.storage}") String storage,
      @Value("${platform.rag-root}") String rag)
      throws IOException {
    this.s = s;
    this.p = p;
    this.auth = auth;
    this.agent = agent;
    this.storage = Path.of(storage).toAbsolutePath().normalize();
    this.rag = Path.of(rag).toAbsolutePath().normalize();
    Files.createDirectories(this.storage.resolve("uploads"));
  }

  record Credentials(
      @Email @NotBlank @Size(max = 190) String email,
      @NotBlank @Size(min = 8, max = 72) String password,
      @Size(max = 80) String name) {}

  record Ask(
      @NotBlank @Size(max = 4000) String question,
      @Pattern(regexp = "evidence|live") String mode,
      @Size(max = 30) List<String> documentIds,
      @NotBlank @Size(max = 100) String idempotencyKey) {}

  record Rename(@NotBlank @Size(max = 120) String title) {}

  @GetMapping("/health")
  Map<String, Object> health() {
    return Map.of("status", "ready", "service", "Enterprise RAG Lab");
  }

  @PostMapping("/auth/login")
  Object login(@Valid @RequestBody Credentials c) {
    return auth.login(c.email(), c.password());
  }

  @PostMapping("/auth/register")
  Object register(@Valid @RequestBody Credentials c) {
    return auth.register(
        c.email(), c.name() == null || c.name().isBlank() ? "研究员" : c.name(), c.password());
  }

  @GetMapping("/auth/me")
  Object me(Principal u) {
    return auth.user(u.getName());
  }

  @PostMapping("/auth/logout")
  Object logout(@RequestHeader("Authorization") String header) {
    auth.logout(header.substring(7));
    return Map.of("ok", true);
  }

  @GetMapping("/overview")
  Object overview(Principal u) {
    var out = new LinkedHashMap<String, Object>();
    out.put("documents", p.docs(u.getName()));
    out.put("conversations", p.conversations(u.getName()));
    out.put("runCount", p.catalog.runCount(u.getName()));
    out.put("recentRuns", runs(u));
    try {
      out.put("agent", agent.health());
      out.put("evaluations", agent.evaluations());
    } catch (Exception e) {
      out.put("agent", Map.of("status", "offline", "modelConfigured", false));
      out.put("evaluations", List.of());
    }
    return out;
  }

  @GetMapping("/documents")
  Object documents(Principal u) {
    return p.docs(u.getName());
  }

  @PostMapping("/documents/sync")
  Object sync(Principal u) {
    p.syncCatalog();
    return p.docs(u.getName());
  }

  @PostMapping("/documents")
  Object upload(Principal u, @RequestParam("file") MultipartFile file) throws IOException {
    String name = Optional.ofNullable(file.getOriginalFilename()).orElse("document");
    name = Path.of(name).getFileName().toString();
    if (name.length() > 240) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "文件名过长");
    String lower = name.toLowerCase(Locale.ROOT),
        ext =
            lower.endsWith(".pdf")
                ? ".pdf"
                : lower.endsWith(".md") ? ".md" : lower.endsWith(".txt") ? ".txt" : "";
    if (ext.isEmpty() || file.isEmpty() || file.getSize() > 20 * 1024 * 1024)
      throw new ResponseStatusException(
          HttpStatus.BAD_REQUEST, "请上传不超过 20 MB 的 PDF、TXT 或 Markdown 文件");
    if (ext.equals(".pdf")) {
      try (var in = file.getInputStream()) {
        if (!new String(in.readNBytes(5), java.nio.charset.StandardCharsets.US_ASCII)
            .equals("%PDF-"))
          throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "文件不是有效 PDF");
      }
    }
    String id = Store.id(), stored = id + ext;
    Path dest = storage.resolve("uploads").resolve(stored);
    try (var in = file.getInputStream()) {
      Files.copy(in, dest);
    }
    try {
      s.jdbc.update(
          "INSERT INTO"
              + " documents(id,user_id,title,file_name,stored_name,source_kind,doc_status,byte_size,created_at)"
              + " VALUES(?,?,?,?,?,?,?,?,?)",
          id,
          u.getName(),
          name,
          name,
          stored,
          "upload",
          "PROCESSING",
          file.getSize(),
          Store.now());
    } catch (Exception e) {
      Files.deleteIfExists(dest);
      throw e;
    }
    p.ingest(id, u.getName(), name, stored);
    return s.docView(s.one("SELECT * FROM documents WHERE id=? AND user_id=?", id, u.getName()));
  }

  @PostMapping("/documents/{id}/retry")
  Object retryDocument(Principal u, @PathVariable String id) {
    var d =
        s.one(
            "SELECT * FROM documents WHERE id=? AND user_id=? AND source_kind='upload'",
            id,
            u.getName());
    if (!"FAILED".equals(d.get("doc_status")))
      throw new ResponseStatusException(HttpStatus.CONFLICT, "只有失败的文档可以重试");
    s.jdbc.update(
        "UPDATE documents SET doc_status='PROCESSING',error_message=NULL WHERE id=? AND user_id=?",
        id,
        u.getName());
    p.ingest(id, u.getName(), d.get("file_name").toString(), d.get("stored_name").toString());
    return Map.of("status", "PROCESSING");
  }

  @DeleteMapping("/documents/{id}")
  Object deleteDocument(Principal u, @PathVariable String id) throws IOException {
    var d =
        s.one(
            "SELECT * FROM documents WHERE id=? AND user_id=? AND source_kind='upload'",
            id,
            u.getName());
    agent.delete(id, u.getName());
    s.jdbc.update("DELETE FROM documents WHERE id=? AND user_id=?", id, u.getName());
    Path target = storage.resolve("uploads").resolve(d.get("stored_name").toString()).normalize();
    if (target.getParent().equals(storage.resolve("uploads"))) Files.deleteIfExists(target);
    return Map.of("deleted", true);
  }

  @GetMapping("/documents/{id}/file")
  ResponseEntity<Resource> file(Principal u, @PathVariable String id) throws IOException {
    var d =
        s.one(
            "SELECT * FROM documents WHERE id=? AND (user_id=? OR source_kind='benchmark')",
            id,
            u.getName());
    Path base =
        d.get("source_kind").equals("benchmark")
            ? rag.resolve("ui/data/financebench")
            : storage.resolve("uploads");
    String filename =
        d.get("source_kind").equals("benchmark")
            ? d.get("file_name").toString()
            : d.get("stored_name").toString();
    Path target = base.resolve(filename).normalize();
    if (!target.getParent().equals(base) || !Files.isRegularFile(target))
      throw new ResponseStatusException(HttpStatus.NOT_FOUND, "文件不存在");
    return ResponseEntity.ok()
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.inline()
                .filename(d.get("file_name").toString(), java.nio.charset.StandardCharsets.UTF_8)
                .build()
                .toString())
        .contentType(filename.endsWith(".pdf") ? MediaType.APPLICATION_PDF : MediaType.TEXT_PLAIN)
        .body(new FileSystemResource(target));
  }

  @GetMapping("/conversations")
  Object conversations(Principal u) {
    return p.conversations(u.getName());
  }

  @PostMapping("/conversations")
  Object createConversation(Principal u) {
    return p.createConversation(u.getName());
  }

  @PatchMapping("/conversations/{id}")
  Object rename(Principal u, @PathVariable String id, @Valid @RequestBody Rename b) {
    s.conversation(id, u.getName());
    s.jdbc.update(
        "UPDATE conversations SET title=?,updated_at=? WHERE id=? AND user_id=?",
        b.title(),
        Store.now(),
        id,
        u.getName());
    return p.conversationView(s.conversation(id, u.getName()));
  }

  @DeleteMapping("/conversations/{id}")
  Object deleteConversation(Principal u, @PathVariable String id) {
    s.conversation(id, u.getName());
    if (!s.list(
            "SELECT id FROM agent_runs WHERE conversation_id=? AND user_id=? AND run_status IN"
                + " ('QUEUED','RUNNING')",
            id,
            u.getName())
        .isEmpty()) throw new ResponseStatusException(HttpStatus.CONFLICT, "请先停止正在执行的任务");
    p.tx.executeWithoutResult(
        t -> {
          s.jdbc.update(
              "DELETE FROM messages WHERE conversation_id=? AND user_id=?", id, u.getName());
          s.jdbc.update(
              "DELETE FROM agent_runs WHERE conversation_id=? AND user_id=?", id, u.getName());
          s.jdbc.update("DELETE FROM conversations WHERE id=? AND user_id=?", id, u.getName());
        });
    return Map.of("deleted", true);
  }

  @GetMapping("/conversations/{id}/messages")
  Object messages(Principal u, @PathVariable String id) {
    return p.messages(id, u.getName());
  }

  @PostMapping("/conversations/{id}/messages")
  Object ask(Principal u, @PathVariable String id, @Valid @RequestBody Ask b) {
    return p.start(
        u.getName(),
        id,
        b.question().strip(),
        b.mode() == null ? "evidence" : b.mode(),
        b.documentIds() == null ? List.of() : b.documentIds(),
        b.idempotencyKey());
  }

  @GetMapping("/runs")
  Object runs(Principal u) {
    return s
        .list(
            "SELECT * FROM agent_runs WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
            u.getName())
        .stream()
        .map(s::runView)
        .toList();
  }

  @GetMapping("/runs/{id}")
  Object run(Principal u, @PathVariable String id) {
    return s.run(id, u.getName());
  }

  @PostMapping("/runs/{id}/cancel")
  Object cancel(Principal u, @PathVariable String id) {
    return p.cancel(id, u.getName());
  }

  @GetMapping(value = "/runs/{id}/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  SseEmitter events(Principal u, @PathVariable String id) {
    String owner = u.getName();
    s.run(id, owner);
    var emitter = new SseEmitter(240000L);
    var closed = new java.util.concurrent.atomic.AtomicBoolean(false);
    emitter.onCompletion(() -> closed.set(true));
    emitter.onTimeout(() -> closed.set(true));
    emitter.onError(e -> closed.set(true));
    Thread.ofVirtual()
        .start(
            () -> {
              try {
                String previous = "";
                while (!closed.get()) {
                  var state = s.run(id, owner);
                  String current = s.encode(state);
                  if (!current.equals(previous)) {
                    emitter.send(SseEmitter.event().name("snapshot").data(state));
                    previous = current;
                  }
                  if (!List.of("QUEUED", "RUNNING").contains(state.get("status"))) {
                    emitter.complete();
                    break;
                  }
                  Thread.sleep(300);
                }
              } catch (Exception e) {
                emitter.completeWithError(e);
              }
            });
    return emitter;
  }

  @GetMapping("/evaluations")
  Object evaluations() {
    return agent.evaluations();
  }

  @GetMapping("/evaluations/{id}")
  Object evaluation(@PathVariable String id) {
    if (!List.of("baseline", "planner", "optimized").contains(id))
      throw new ResponseStatusException(HttpStatus.NOT_FOUND, "评测不存在");
    return agent.evaluation(id);
  }
}
