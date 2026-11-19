# Enterprise RAG Lab 全栈研究平台

React 与 TypeScript 前端、Spring Boot 业务后端、Python RAG 适配服务和 MySQL 组成的本地研究平台。新增代码集中在 `platform/`，原项目 `src/` 的检索、生成和评测算法保持原样。

## 打开平台

双击本目录的 `start.command`，或在原项目目录执行：

```bash
python3 platform/scripts/platform.py start
```

访问 http://127.0.0.1:9080 。本地演示账号：

- 邮箱：`demo@raglab.local`
- 密码：`RagLab2026!`

也可在登录页创建自己的账号。个人上传、会话、消息和任务按账号隔离；FinanceBench 财报为共享只读资料。

首次安装或修改前后端代码后重新构建：

```bash
python3 platform/scripts/platform.py build
python3 platform/scripts/platform.py start
```

开发需要 JDK 21、Maven、Node.js、Docker Desktop，以及原项目可用的 `.venv`。Maven 可继续使用已经配置的 IDEA 自带版本。Docker Desktop 应先启动。

检查与停止：

```bash
python3 platform/scripts/platform.py status
python3 platform/scripts/platform.py stop
```

停止保留数据库和上传文件；不要使用删除数据卷的命令清理项目。

## 已实现功能

| 页面         | 功能                                                                           |
| ------------ | ------------------------------------------------------------------------------ |
| 研究概览     | 真实文档数量、固定评测集、已有实验指标、当前用户任务与最近研究                 |
| 知识库       | 基准财报同步、名称搜索、个人 PDF/TXT/Markdown 上传、解析状态、原文件预览与删除 |
| 智能问答     | 会话新建、切换、重命名、删除；文档范围；流式回答；执行过程；取消；来源与页码   |
| 评测中心     | 三组真实实验对比、46 道题的回答与参考答案、证据页命中、搜索与分页              |
| 任务记录     | 实时状态、耗时、错误原因、取消、返回原会话                                     |
| 账号与工作区 | 注册登录、JWT、退出失效、服务连接与模型配置状态                                |

### 两种问答方式

**证据预览**：不调用模型，将检索到的文档原文及页码显示出来。公共资料优先复用原项目已解析的父块；私有上传使用平台独立文字证据索引。此模式不会伪装成模型结论。

**模型问答**：使用原项目 `src/.env` 中的模型配置。未选择具体文档时，公共财报调用原有 `EvidenceRetriever`，复用 Planner、混合检索、证据组装和门控输出；指定文档时，使用限定范围的文本证据检索，再流式生成带引用的答案。

选择全部文档时，原 Agent 检索公共基准库，并合并当前用户的私有文本证据；也可在范围选择器中只选个人文档。个人资料不会写进共享 Chroma，当前不进行向量化或表格结构解析。

当前已有模型配置在本次验证中返回 401。已按用户选择先完成平台，生成入口保留，后续更新有效 `src/.env` 配置并重启服务后再验证；不会用模拟答案冒充模型输出。

模型服务有实际调用费用。首次使用原检索路径可能需要加载本地嵌入与重排模型，冷启动较慢。检索或模型失败会明确显示失败，不以历史回答替代。

### 评测数据

页面读取以下既有报告，不会自动运行整套付费评测：

- 基线：`financebench_enterprise_contract_final.json`、`ragas_enterprise_contract_final.json`
- Agent Planner：`financebench_agent_planner.json`、`ragas_agent_planner_full.json`
- 证据槽位优化：`financebench_slot_aware_final.json`、`ragas_slot_aware_final_v2.json`

答案正确性、上下文召回与忠实度来自 RAGAS 生成报告；证据页命中率来自检索报告。指标仅代表对应固定实验集，不是线上质量保证。

## 服务职责与数据流

| 部分     | 职责与入口                                                                           |
| -------- | ------------------------------------------------------------------------------------ |
| 浏览器   | `frontend/src/App.tsx` 管理工作区；`pages/` 分离页面，`components/` 复用界面，`api.ts` 管理请求和 SSE                     |
| Java     | 身份与资源权限、业务状态、任务调度、数据库事务、推理调用、结果与引用持久化           |
| Python   | 已有 RAG 的适配、上传文字提取、证据检索、模型流式输出和已有评测报告读取              |
| MySQL    | 用户、会话、消息、文档元数据、任务、请求去重与登录会话                               |
| 平台存储 | `storage/uploads/` 保存个人原文件；`storage/evidence.sqlite3` 保存隔离的文字证据索引 |

一次提问的流程：前端提交问题和幂等键，Java 检查身份与文档归属，在短事务中创建消息和任务，后台工作线程调用 Python，Python 返回阶段、引用、内容和终态事件，Java 保存执行快照并通过 SSE 返回页面。

所有权由已认证的 Java 用户决定；内部服务使用独立随机凭证。不会信任浏览器提交的用户 ID。数据库事务不跨越长时间模型调用。

## 目录与关键代码

```text
platform/
  frontend/                 React 应用与生产构建
  backend/                  Spring Boot 服务
    src/main/java/lab/platform/
      AuthService.java      JWT、密码哈希、登录失效
      SecurityConfig.java   身份校验与安全过滤链
      ApiController.java    REST、文件、SSE 端点
      PlatformService.java  状态、幂等、执行和取消
      Store.java            业务查询与响应映射
      CatalogMapper.java    MyBatis 文档查询
      AgentClient.java      普通 HTTP 与流式客户端
  agent_service/app.py      原 RAG 的薄适配与私有证据索引
  tests/                    跨语言与浏览器验证
  scripts/platform.py       构建、启动、停止与状态
  compose.yaml              独立 MySQL 容器和数据卷
  .env.example              配置模板
```

## 配置与端口

| 服务            | 默认地址         |
| --------------- | ---------------- |
| Web 与 Java API | `127.0.0.1:9080` |
| 内部 Python     | `127.0.0.1:9081` |
| 平台 MySQL      | `127.0.0.1:3308` |
| 前端开发服务器  | `127.0.0.1:5175` |

首次启动自动生成 `.env`，保存独立的数据库密码、JWT 密钥和内部服务凭证，权限为 600，已加入 `.gitignore`。不需要在浏览器填写模型密钥；现有模型配置继续从 `src/.env` 读取。

更换端口或 JDK 路径时修改 `.env`。MySQL 首次初始化后，修改密码变量不会自动修改已持久化的数据库密码；需在数据库中同步调整，不能直接删除数据卷。

仅本机监听。若部署到公网，需额外配置 HTTPS、反向代理、账号管理和入口限流，并关闭或更改公开演示账号；本版不宣称生产多实例能力。

## 本地开发

前端热更新：

```bash
cd platform/frontend
npm ci
npm run dev
```

开发服务器将 `/api` 代理到 Java 的 9080 端口。修改后运行 `npm run build` 更新 Java 托管的静态资源。

Java 使用 Maven 项目 `platform/backend/pom.xml`。IDEA 使用 JDK 21。项目依赖通过 `platform/maven-settings.xml` 固定使用 Maven Central。

Python 复用原项目 `.venv`；适配器所需依赖列在 `agent_service/requirements.txt`。不要为运行平台重建原 Chroma，也不需要重新运行整套评测。

## 测试

Java 单元及集成测试，使用 H2 测试库和模拟下游，不修改平台 MySQL：

```bash
cd platform/backend
mvn -s ../maven-settings.xml test
```

Python 私有证据、内部认证、路径校验与任务去重测试：

```bash
cd platform
PYTHONPATH="$PWD" ../.venv/bin/python -m pytest tests/test_agent_service.py -q
```

真实完整服务测试，启动平台后执行；会创建隔离的测试账号和文档：

```bash
cd platform
../.venv/bin/python tests/e2e_platform.py
```

浏览器测试，使用前端安装的 Playwright 与本机 Chrome；其他系统可设置 `CHROME_PATH`，或安装 Playwright Chromium：

```bash
cd platform/frontend
npm ci
cd ..
node tests/browser.cjs
```

`tests/live_query.py` 会用配置的真实模型对一条公共财报问题执行完整原 RAG 路径，需有效密钥，并会产生模型调用费用；不会在普通测试中自动执行。

## 已验证的工程边界

- 幂等由用户、幂等键、请求指纹与数据库唯一约束共同处理；不同内容复用同一键返回冲突。
- 执行线程和等待队列有上限，队列满时任务明确失败。
- 重启把遗留运行任务标记为中断，不自动重复执行可能已经完成的下游请求。
- Python 任务记录是有界的进程内诊断信息；业务结果由 Java 与 MySQL 持久化。
- 取消尽力传递给下游，不保证能撤回已发出的模型请求或立即停止原同步检索线程。
- SSE 断开不等同于业务取消，前端可重新连接或使用状态查询；原文件仍按用户检查权限。
- 私有资料的基于文本检索和原公共库混合检索是两条明确区分的路径；不将前者包装为完整向量检索。

## 五分钟演示顺序

1. 登录演示账号，查看文档数与真实实验指标。
2. 打开一份基准财报，查看原文件。
3. 在证据模式提问并打开引用，核对页码和原文。
4. 上传测试 TXT 或 PDF，选择它作为检索范围并完成问答。
5. 查看任务状态、耗时和执行过程；演示会话重命名。
6. 在评测中心切换方案，打开单题比较生成回答与参考答案。
7. 介绍 Java 与 Python 的职责、幂等与资源隔离，以及当前单机边界。
