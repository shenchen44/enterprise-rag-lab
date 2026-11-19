package lab.platform;

import java.util.*;
import org.apache.ibatis.annotations.*;

@Mapper
public interface CatalogMapper {
  @Select(
      "SELECT * FROM documents WHERE user_id=#{owner} OR source_kind='benchmark' ORDER BY"
          + " source_kind,title")
  List<Map<String, Object>> documents(String owner);

  @Select("SELECT COUNT(*) FROM agent_runs WHERE user_id=#{owner}")
  long runCount(String owner);
}
