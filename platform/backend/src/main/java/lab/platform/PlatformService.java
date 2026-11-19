package lab.platform;

import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PlatformService {
  final Store s;
  final AgentClient agent;
  final AuthService auth;
  final CatalogMapper catalog;
  final TransactionTemplate tx;
  final ThreadPoolExecutor workers =
      new ThreadPoolExecutor(
          2,
          2,
          30,
          TimeUnit.SECONDS,
          new ArrayBlockingQueue<>(8),
          r -> {
            var t = new Thread(r, "rag-worker");
            t.setDaemon(true);
            return t;
          });
  final ConcurrentHashMap<String, AtomicBoolean> cancellations = new ConcurrentHashMap<>();
  final Logger log = LoggerFactory.getLogger(PlatformService.class);

  @Value("${platform.demo}")
  boolean demo;

  PlatformService(
      Store s,
      AgentClient agent,
      AuthService auth,
      CatalogMapper catalog,
      PlatformTransactionManager tm) {
    this.s = s;
    this.agent = agent;
    this.auth = auth;
    this.catalog = catalog;
    this.tx = new TransactionTemplate(tm);
  }

  @EventListener(ApplicationReadyEvent.class)
  public void initialize() {
    s.jdbc.update(
        "UPDATE agent_runs SET run_status='INTERRUPTED',error_message=?,updated_at=? WHERE"
            + " run_status IN ('QUEUED','RUNNING')",
        "业务服务已重启，执行结果可能不确定；请确认后重新发起",
        Store.now());
    s.jdbc.update(
        "UPDATE messages SET msg_status='INTERRUPTED' WHERE msg_status IN ('QUEUED','RUNNING')");
    s.jdbc.update(
        "UPDATE documents SET doc_status='FAILED',error_message='解析服务已中断，请重试' WHERE"
            + " doc_status='PROCESSING'");
    if (demo && s.list("SELECT id FROM app_users WHERE email=?", "demo@raglab.local").isEmpty())
      auth.register("demo@raglab.local", "研究员", "RagLab2026!");
    try {
      syncCatalog();
    } catch (Exception e) {
      log.warn("Catalog sync unavailable at startup; retry from UI");
    }
  }

  void syncCatalog() {
    for (var d : agent.catalog()) {
      if (s.list("SELECT id FROM documents WHERE id=?", d.get("id")).isEmpty())
        s.jdbc.update(
            "INSERT INTO"
                + " documents(id,user_id,title,file_name,source_kind,doc_status,pages,chunks,byte_size,created_at)"
                + " VALUES(?,?,?,?,?,?,?,?,?,?)",
            d.get("id"),
            "public",
            d.get("title"),
            d.get("fileName"),
            "benchmark",
            "READY",
            d.get("pages"),
            d.get("chunks"),
            d.get("bytes"),
            Store.now());
      else
        s.jdbc.update(
            "UPDATE documents SET pages=?,chunks=? WHERE id=?",
            d.get("pages"),
            d.get("chunks"),
            d.get("id"));
    }
  }

  List<Map<String, Object>> docs(String owner) {
    return catalog.documents(owner).stream().map(s::docView).toList();
  }

  Map<String, Object> createConversation(String owner) {
    String id = Store.id(), now = Store.now();
    s.jdbc.update("INSERT INTO conversations VALUES(?,?,?,?,?)", id, owner, "新对话", now, now);
    return conversationView(s.conversation(id, owner));
  }

  Map<String, Object> conversationView(Map<String, Object> m) {
    return Map.of(
        "id",
        m.get("id"),
        "title",
        m.get("title"),
        "createdAt",
        m.get("created_at"),
        "updatedAt",
        m.get("updated_at"));
  }

  List<Map<String, Object>> conversations(String owner) {
    return s
        .list("SELECT * FROM conversations WHERE user_id=? ORDER BY updated_at DESC", owner)
        .stream()
        .map(this::conversationView)
        .toList();
  }

  List<Map<String, Object>> messages(String id, String owner) {
    s.conversation(id, owner);
    return s
        .list(
            "SELECT * FROM messages WHERE conversation_id=? AND user_id=? ORDER BY created_at,id",
            id,
            owner)
        .stream()
        .map(
            m -> {
              var o = new LinkedHashMap<String, Object>();
              o.put("id", m.get("id"));
              o.put("role", m.get("role_name"));
              o.put("content", m.get("content"));
              o.put("status", m.get("msg_status"));
              o.put("citations", s.decode(m.get("citations_json")));
              o.put("trace", s.decode(m.get("trace_json")));
              o.put("createdAt", m.get("created_at"));
              return (Map<String, Object>) o;
            })
        .toList();
  }

  Map<String, Object> start(
      String owner,
      String conversation,
      String question,
      String mode,
      List<String> ids,
      String key) {
    s.conversation(conversation, owner);
    for (String id : ids) {
      var d =
          s.one(
              "SELECT * FROM documents WHERE id=? AND (user_id=? OR source_kind='benchmark')",
              id,
              owner);
      if (!"READY".equals(d.get("doc_status")))
        throw new ResponseStatusException(HttpStatus.CONFLICT, "文档尚未解析完成");
    }
    String fingerprint =
        AuthService.hash(s.encode(List.of(conversation, question, mode, new TreeSet<>(ids))));
    var existing =
        s.list("SELECT * FROM agent_runs WHERE user_id=? AND idempotency_key=?", owner, key);
    if (!existing.isEmpty()) return duplicate(existing.getFirst(), fingerprint);
    String id = Store.id(), message = Store.id(), now = Store.now();
    try {
      tx.executeWithoutResult(
          status -> {
            s.jdbc.update(
                "INSERT INTO"
                    + " agent_runs(id,user_id,conversation_id,message_id,run_status,answer_mode,question,answer,citations_json,trace_json,idempotency_key,created_at,updated_at,request_hash)"
                    + " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                id,
                owner,
                conversation,
                message,
                "QUEUED",
                mode,
                question,
                "",
                "[]",
                "[]",
                key,
                now,
                now,
                fingerprint);
            s.jdbc.update(
                "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)",
                Store.id(),
                conversation,
                owner,
                "user",
                question,
                "SUCCEEDED",
                "[]",
                "[]",
                now);
            s.jdbc.update(
                "INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)",
                message,
                conversation,
                owner,
                "assistant",
                "",
                "QUEUED",
                "[]",
                "[]",
                Instant.now().plusMillis(1).toString());
            s.jdbc.update(
                "UPDATE conversations SET title=CASE WHEN title='新对话' THEN ? ELSE title"
                    + " END,updated_at=? WHERE id=? AND user_id=?",
                question.substring(0, Math.min(question.length(), 60)),
                now,
                conversation,
                owner);
          });
    } catch (DuplicateKeyException e) {
      return duplicate(
          s.one("SELECT * FROM agent_runs WHERE user_id=? AND idempotency_key=?", owner, key),
          fingerprint);
    }
    var cancel = new AtomicBoolean(false);
    cancellations.put(id, cancel);
    try {
      workers.execute(() -> execute(id, owner, conversation, message, question, mode, ids, cancel));
    } catch (RejectedExecutionException e) {
      finish(id, message, "FAILED", "", "[]", "[]", "任务较多，请稍后重试", 0);
      cancellations.remove(id);
    }
    return s.run(id, owner);
  }

  Map<String, Object> duplicate(Map<String, Object> row, String fp) {
    if (!fp.equals(row.get("request_hash")))
      throw new ResponseStatusException(HttpStatus.CONFLICT, "同一请求标识不能用于不同的问题");
    return s.runView(row);
  }

  void execute(
      String id,
      String owner,
      String conversation,
      String message,
      String question,
      String mode,
      List<String> ids,
      AtomicBoolean cancel) {
    long start = System.nanoTime();
    StringBuilder answer = new StringBuilder();
    List<Map<String, Object>> trace = new ArrayList<>();
    Object[] citations = {List.of()};
    boolean[] done = {false};
    long[] lastSave = {0};
    try {
      if (cancel.get()) throw new CancellationException();
      s.jdbc.update(
          "UPDATE agent_runs SET run_status='RUNNING',updated_at=? WHERE id=? AND"
              + " run_status='QUEUED'",
          Store.now(),
          id);
      s.jdbc.update("UPDATE messages SET msg_status='RUNNING' WHERE id=?", message);
      log.info("run={} user={} started mode={}", id, owner, mode);
      try (var stream =
          agent
              .query(
                  Map.of(
                      "taskId",
                      id,
                      "owner",
                      owner,
                      "question",
                      question,
                      "mode",
                      mode,
                      "documentIds",
                      ids,
                      "history",
                      s.list(
                          "SELECT role_name AS role,content FROM messages WHERE conversation_id=?"
                              + " AND user_id=? AND msg_status='SUCCEEDED' ORDER BY created_at DESC"
                              + " LIMIT 8",
                          conversation,
                          owner)))
              .toStream()) {
        var it = stream.iterator();
        while (it.hasNext()) {
          if (cancel.get()) throw new CancellationException();
          var event = s.json.readTree(it.next());
          String type = event.path("type").asText();
          if (type.equals("stage")) {
            trace.add(
                Map.of(
                    "stage",
                    event.path("stage").asText(),
                    "detail",
                    event.path("detail").asText(),
                    "at",
                    Store.now()));
          }
          if (type.equals("evidence")) {
            citations[0] = s.json.convertValue(event.path("citations"), Object.class);
            trace.add(
                Map.of(
                    "stage",
                    event.path("pipeline").asText(),
                    "detail",
                    "找到 " + event.path("citations").size() + " 条证据",
                    "at",
                    Store.now()));
          }
          if (type.equals("delta")) answer.append(event.path("text").asText());
          if (type.equals("error"))
            throw new IllegalStateException(event.path("message").asText("Agent 执行失败"));
          if (type.equals("done")) done[0] = true;
          if (System.currentTimeMillis() - lastSave[0] > 250 || type.equals("done")) {
            s.jdbc.update(
                "UPDATE agent_runs SET answer=?,citations_json=?,trace_json=?,updated_at=? WHERE"
                    + " id=? AND run_status='RUNNING'",
                answer.toString(),
                s.encode(citations[0]),
                s.encode(trace),
                Store.now(),
                id);
            lastSave[0] = System.currentTimeMillis();
          }
        }
      }
      if (!done[0]) throw new IllegalStateException("推理流提前结束，回答可能不完整");
      if (cancel.get()) throw new CancellationException();
      finish(
          id,
          message,
          "SUCCEEDED",
          answer.toString(),
          s.encode(citations[0]),
          s.encode(trace),
          null,
          (System.nanoTime() - start) / 1000000);
    } catch (CancellationException e) {
      finish(
          id,
          message,
          "CANCELLED",
          answer.toString(),
          s.encode(citations[0]),
          s.encode(trace),
          "任务已取消；部分内容可能不完整",
          (System.nanoTime() - start) / 1000000);
    } catch (Exception e) {
      log.warn("run={} failed type={}", id, e.getClass().getSimpleName());
      String error =
          e instanceof IllegalStateException ? e.getMessage() : "推理服务暂不可用或执行超时，请检查服务状态后重试";
      finish(
          id,
          message,
          cancel.get() ? "CANCELLED" : "FAILED",
          answer.toString(),
          s.encode(citations[0]),
          s.encode(trace),
          error,
          (System.nanoTime() - start) / 1000000);
    } finally {
      cancellations.remove(id);
      log.info("run={} finished", id);
    }
  }

  void finish(
      String id,
      String message,
      String status,
      String answer,
      String citations,
      String trace,
      String error,
      long ms) {
    tx.executeWithoutResult(
        t -> {
          int n =
              s.jdbc.update(
                  "UPDATE agent_runs SET"
                      + " run_status=?,answer=?,citations_json=?,trace_json=?,error_message=?,latency_ms=?,updated_at=?"
                      + " WHERE id=? AND run_status IN ('QUEUED','RUNNING')",
                  status,
                  answer,
                  citations,
                  trace,
                  error,
                  ms,
                  Store.now(),
                  id);
          if (n > 0)
            s.jdbc.update(
                "UPDATE messages SET content=?,msg_status=?,citations_json=?,trace_json=? WHERE"
                    + " id=?",
                answer,
                status,
                citations,
                trace,
                message);
        });
  }

  Map<String, Object> cancel(String id, String owner) {
    var run = s.run(id, owner);
    var c = cancellations.get(id);
    if (c != null) c.set(true);
    String status = run.get("status").toString();
    if (status.equals("QUEUED") || status.equals("RUNNING")) {
      finish(
          id,
          run.get("messageId").toString(),
          "CANCELLED",
          Objects.toString(run.get("answer"), ""),
          s.encode(run.get("citations")),
          s.encode(run.get("trace")),
          "任务已取消；下游取消为尽力传递",
          0);
      workersSubmitCancel(id);
    }
    return s.run(id, owner);
  }

  void workersSubmitCancel(String id) {
    Thread.ofVirtual().start(() -> agent.cancel(id));
  }

  void ingest(String id, String owner, String name, String stored) {
    try {
      workers.execute(
          () -> {
            try {
              var info =
                  agent.ingest(
                      Map.of(
                          "documentId",
                          id,
                          "owner",
                          owner,
                          "fileName",
                          name,
                          "storedName",
                          stored));
              s.jdbc.update(
                  "UPDATE documents SET doc_status='READY',pages=?,chunks=? WHERE id=? AND"
                      + " user_id=?",
                  info.get("pages"),
                  info.get("chunks"),
                  id,
                  owner);
            } catch (Exception e) {
              s.jdbc.update(
                  "UPDATE documents SET doc_status='FAILED',error_message=? WHERE id=? AND"
                      + " user_id=?",
                  "解析失败：文件无可提取文本或解析服务不可用",
                  id,
                  owner);
            }
          });
    } catch (RejectedExecutionException e) {
      s.jdbc.update(
          "UPDATE documents SET doc_status='FAILED',error_message=? WHERE id=?",
          "任务队列已满，请删除后重试",
          id);
    }
  }

  @PreDestroy
  public void stop() {
    workers.shutdownNow();
  }
}
