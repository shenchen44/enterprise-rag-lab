package lab.platform;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {
  final Store store;
  final SecretKey key;
  final BCryptPasswordEncoder passwords = new BCryptPasswordEncoder();

  public AuthService(Store store, @Value("${platform.jwt-secret}") String secret) {
    this.store = store;
    if (secret.length() < 32)
      throw new IllegalStateException("PLATFORM_JWT_SECRET must contain at least 32 characters");
    key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
  }

  static String hash(String token) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8)));
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }

  public Map<String, Object> register(String email, String name, String password) {
    if (password.length() < 8 || password.length() > 72)
      throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "密码长度需为 8 至 72 位");
    String id = Store.id();
    try {
      store.jdbc.update(
          "INSERT INTO app_users VALUES(?,?,?,?,?)",
          id,
          email.toLowerCase(Locale.ROOT).strip(),
          name.strip(),
          passwords.encode(password),
          Store.now());
    } catch (DuplicateKeyException e) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "该邮箱已注册");
    }
    return login(email, password);
  }

  public Map<String, Object> login(String email, String password) {
    var users =
        store.list("SELECT * FROM app_users WHERE email=?", email.toLowerCase(Locale.ROOT).strip());
    if (users.isEmpty()
        || !passwords.matches(password, users.getFirst().get("password_hash").toString()))
      throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "邮箱或密码不正确");
    var u = users.getFirst();
    long until = System.currentTimeMillis() + 8 * 60 * 60 * 1000L;
    String token =
        Jwts.builder()
            .id(Store.id())
            .subject(u.get("id").toString())
            .issuedAt(new Date())
            .expiration(new Date(until))
            .signWith(key)
            .compact();
    store.jdbc.update("DELETE FROM app_sessions WHERE expires_at<?", System.currentTimeMillis());
    store.jdbc.update("INSERT INTO app_sessions VALUES(?,?,?)", hash(token), u.get("id"), until);
    return Map.of("token", token, "user", user(u.get("id").toString()));
  }

  public String verify(String token) {
    try {
      String id =
          Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload().getSubject();
      var row =
          store.list(
              "SELECT user_id FROM app_sessions WHERE token_hash=? AND expires_at>?",
              hash(token),
              System.currentTimeMillis());
      if (row.isEmpty() || !id.equals(row.getFirst().get("user_id"))) return null;
      return id;
    } catch (Exception e) {
      return null;
    }
  }

  public Map<String, Object> user(String id) {
    var u = store.one("SELECT id,email,name FROM app_users WHERE id=?", id);
    return Map.of("id", u.get("id"), "email", u.get("email"), "name", u.get("name"));
  }

  public void logout(String token) {
    store.jdbc.update("DELETE FROM app_sessions WHERE token_hash=?", hash(token));
  }
}
