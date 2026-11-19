package lab.platform;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class Store {
  final JdbcTemplate jdbc;
  final ObjectMapper json;

  public Store(JdbcTemplate jdbc, ObjectMapper json) {
    this.jdbc = jdbc;
    this.json = json;
  }

  static String id() {
    return UUID.randomUUID().toString();
  }

  static String now() {
    return Instant.now().toString();
  }

  String encode(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  Object decode(Object value) {
    if (value == null) return List.of();
    try {
      return json.readValue(value.toString(), Object.class);
    } catch (Exception e) {
      return List.of();
    }
  }

  Map<String, Object> one(String sql, Object... args) {
    var all = jdbc.queryForList(sql, args);
    if (all.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "资源不存在或不可访问");
    return all.getFirst();
  }

  List<Map<String, Object>> list(String sql, Object... args) {
    return jdbc.queryForList(sql, args);
  }

  Map<String, Object> conversation(String id, String owner) {
    return one("SELECT * FROM conversations WHERE id=? AND user_id=?", id, owner);
  }

  Map<String, Object> run(String id, String owner) {
    return runView(one("SELECT * FROM agent_runs WHERE id=? AND user_id=?", id, owner));
  }

  Map<String, Object> runView(Map<String, Object> m) {
    var out = new LinkedHashMap<String, Object>();
    out.put("id", m.get("id"));
    out.put("conversationId", m.get("conversation_id"));
    out.put("messageId", m.get("message_id"));
    out.put("status", m.get("run_status"));
    out.put("mode", m.get("answer_mode"));
    out.put("question", m.get("question"));
    out.put("answer", m.get("answer"));
    out.put("citations", decode(m.get("citations_json")));
    out.put("trace", decode(m.get("trace_json")));
    out.put("error", m.get("error_message"));
    out.put("latencyMs", m.get("latency_ms"));
    out.put("createdAt", m.get("created_at"));
    out.put("updatedAt", m.get("updated_at"));
    return out;
  }

  Map<String, Object> docView(Map<String, Object> m) {
    var o = new LinkedHashMap<String, Object>();
    for (String k : List.of("id", "title", "pages", "chunks")) o.put(k, m.get(k));
    o.put("fileName", m.get("file_name"));
    o.put("kind", m.get("source_kind"));
    o.put("status", m.get("doc_status"));
    o.put("bytes", m.get("byte_size"));
    o.put("createdAt", m.get("created_at"));
    o.put("error", m.get("error_message"));
    return o;
  }
}
