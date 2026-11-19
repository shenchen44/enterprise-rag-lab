package lab.platform;

import java.time.Duration;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

@Component
public class AgentClient {
  final RestClient rest;
  final WebClient web;

  AgentClient(@Value("${agent.url}") String url, @Value("${agent.token}") String token) {
    var factory = new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(5));
    factory.setReadTimeout(Duration.ofSeconds(120));
    rest =
        RestClient.builder()
            .baseUrl(url)
            .requestFactory(factory)
            .defaultHeader("X-Internal-Token", token)
            .build();
    web = WebClient.builder().baseUrl(url).defaultHeader("X-Internal-Token", token).build();
  }

  @SuppressWarnings("unchecked")
  List<Map<String, Object>> catalog() {
    return rest.get().uri("/internal/catalog").retrieve().body(List.class);
  }

  @SuppressWarnings("unchecked")
  Map<String, Object> health() {
    return rest.get().uri("/internal/health").retrieve().body(Map.class);
  }

  Object evaluations() {
    return rest.get().uri("/internal/evaluations").retrieve().body(Object.class);
  }

  Object evaluation(String id) {
    return rest.get().uri("/internal/evaluations/{id}", id).retrieve().body(Object.class);
  }

  @SuppressWarnings("unchecked")
  Map<String, Object> ingest(Map<String, Object> data) {
    return rest.post().uri("/internal/ingest").body(data).retrieve().body(Map.class);
  }

  void delete(String id, String owner) {
    rest.delete()
        .uri(u -> u.path("/internal/documents/{id}").queryParam("owner", owner).build(id))
        .retrieve()
        .toBodilessEntity();
  }

  void cancel(String id) {
    try {
      rest.post().uri("/internal/tasks/{id}/cancel", id).retrieve().toBodilessEntity();
    } catch (Exception ignored) {
    }
  }

  Flux<String> query(Map<String, Object> body) {
    return web.post()
        .uri("/internal/query/stream")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.TEXT_EVENT_STREAM)
        .bodyValue(body)
        .retrieve()
        .bodyToFlux(String.class)
        .timeout(Duration.ofSeconds(180));
  }
}
