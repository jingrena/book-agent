# 智能图书助手 (Smart Book Assistant)

基于 LangGraph 的多智能体图书管理系统，支持 Web UI 和 CLI 两种交互方式。

## 项目架构

```
demo-agent/
├── app.py                  # FastAPI + LangServe 入口（Web UI + REST API）
├── cli.py                  # CLI 命令行交互入口
├── graph.py                # LangGraph StateGraph 主图定义与编译
├── nodes.py                # 图节点函数（护栏、分类、路由、记忆更新）
├── state.py                # 主图与子图的状态定义（TypedDict）
├── specialists.py          # 内置专家定义 + Skill 专家动态加载
├── memory.py               # 长期记忆（JSON 持久化 + LLM 异步提取）
├── llm.py                  # LLM 工厂（ChatOpenAI 兼容接口）
├── rag.py                  # RAG 存储层（TF-IDF 向量存储 + Milvus 可选）
├── guardrails.py           # 输入/输出护栏（注入检测、脱敏）
├── callbacks.py            # 自定义回调（追踪系统、Token 流式）
├── books.json              # 书籍数据（JSON 文件存储）
├── agent_memory.json       # 长期记忆持久化文件
├── docker-compose.yml      # Milvus 向量数据库（可选）
├── requirements.txt        # Python 依赖
├── static/                 # 前端静态资源
│   ├── style.css
│   └── app.js
├── templates/
│   └── index.html          # Web UI 页面
├── tools/                  # 工具层
│   ├── __init__.py         # 工具注册与动态加载
│   ├── core.py             # 核心工具（时间、计算、搜索、上架、天气）
│   └── rag.py              # RAG 语义检索工具
├── workflows/              # 工作流子图
│   ├── __init__.py         # 工作流注册
│   ├── new_book.py         # 新书入库（查重→分类→确认→通知）
│   ├── recommend.py        # 智能推荐（语义检索→个性化推荐）
│   └── inventory.py        # 书籍盘点（统计→报告生成）
└── skills/                 # 可插拔技能模块
    ├── __init__.py
    ├── book_review.py      # 书评生成（查询书籍信息、比较分析）
    └── translator.py       # 多语言翻译（术语词典查询）
```

## 核心能力

### 1. 意图识别与路由

用户输入经输入护栏检查后，通过**关键词匹配 + LLM 兜底**进行意图分类，路由至不同处理链路：

| 路由类型 | 触发条件示例 | 处理方式 |
|---------|------------|---------|
| 快捷回复 | "你好"、"谢谢"、"再见" | 预定义话术直接返回 |
| 工作流 | "上架一本书"、"推荐科幻小说"、"盘点库存" | 进入结构化工作流子图 |
| 专家协作 | 书评、翻译、通用问答等 | 单/多专家 ReAct Agent 链式调用 |

### 2. 专家系统（Specialists）

每个专家是一个独立的 ReAct Agent（LangGraph `create_react_agent`），拥有专属工具和系统提示词：

| 专家 | 身份 | 可用工具 | 来源 |
|------|------|---------|------|
| 检索员 (retriever) | 精准找书，不做推荐 | search_books, search_books_semantic | 内置 |
| 推荐官 (recommender) | 个性化推荐，有温度的推荐理由 | search_books, search_books_semantic | 内置 |
| 图书管理员 (librarian) | 书籍上架与库存管理 | search_books, add_book | 内置 |
| 通用助手 (general) | 通用问答与工具调用 | get_current_time, calculate, search_weather | 内置 |
| 书评家 (critic) | 专业书评撰写、书籍比较分析 | get_book_info, compare_books_info, search_books | skills/ |
| 翻译官 (translator) | 多语言翻译（中英日韩法）| lookup_dictionary | skills/ |

多专家可**链式协作**：上一个专家的输出作为下一个的输入（如 检索员→推荐官）。

### 3. 工作流系统（Workflows）

工作流是独立的 LangGraph 子图，处理结构化多步骤任务：

**新书入库**：
```
查重检测 → 智能分类（规则+LLM） → 确认上架（interrupt 暂停等待用户确认） → 通知
```
- 支持正则 + LLM 双路提取书籍信息（书名、作者、日期）
- `interrupt` 机制实现人机协同确认
- 查重防止重复入库

**智能推荐**：
```
语义检索候选书目 → 结合用户长期记忆做个性化推荐
```
- RAG 语义搜索取代关键词匹配
- 融合用户偏好记忆做个性化排序

**书籍盘点**：
```
统计馆藏（总数+分类分布） → LLM 生成分析报告
```

### 4. RAG 语义检索

- **向量存储**：优先 Milvus，自动回退到自研 TF-IDF 向量存储
- **双索引**：书籍索引 + 记忆索引，支持语义相似度搜索
- **中文友好**：自研分词器支持中英混合文本，unigram + bigram 特征
- 工具 `search_books_semantic` 支持自然语言描述搜索，如"关于宇宙文明兴衰的科幻"

### 5. 记忆系统（短期 + 长期）

**短期记忆（Redis）**：
- LangGraph checkpointer：会话状态暂存，支持中断恢复
- 前端对话历史：7 天 TTL 自动过期
- Sorted Set 索引支持会话列表快速排序

**长期记忆（JSON + RAG 向量）**：
- 每次对话后异步提取用户偏好和事实信息
- JSON 文件持久化 + TF-IDF 向量索引（可选 Milvus）
- 在后续对话中自动注入相关记忆，实现个性化交互

### 6. 安全护栏

**输入护栏**：
- 提示注入检测（中英文关键词/正则匹配）
- 输入长度限制（2000 字符）

**输出护栏**：
- API Key 脱敏
- 密码字段脱敏
- 手机号中间位脱敏

### 7. 可插拔技能系统（Skills）

`skills/` 目录下的模块通过约定式接口自动注册：
- `SPECIALISTS` 列表：定义专家（key、name、system_prompt、tools）
- `KEYWORDS` 列表：路由触发关键词
- `@tool` 装饰器函数：自动发现并注册为工具

新增技能只需在 `skills/` 目录下添加一个 `.py` 文件即可。

### 8. 追踪与可观测性

- 自定义 `Tracer` 系统记录每次请求的全链路耗时与 Token 消耗
- `Span` 级别追踪每个节点的输入/输出 Token 和状态
- Web UI 右侧面板实时展示处理过程与追踪报告
- 支持 SSE 事件流：`thinking`、`route`、`specialist`、`step`、`token`、`done`、`error`

## 启动方式

### 环境准备

```bash
pip install -r requirements.txt
cp .env.example .env  # 配置 OPENAI_BASE_URL、OPENAI_API_KEY 等
```

### 可选：启动 Milvus 向量数据库

```bash
docker compose up -d
```

不启动 Milvus 时，系统自动使用内置 TF-IDF 向量存储。

### Web UI 模式

```bash
python app.py
# 打开浏览器访问 http://localhost:8000
```

Web UI 提供三栏布局：
- **左侧**：会话列表，支持多轮对话管理
- **中间**：聊天区域，SSE 流式输出
- **右侧**：过程/追踪/记忆/书库/技能 面板

### CLI 模式

```bash
python cli.py
```

CLI 支持命令：`quit` 退出、`memory` 查看记忆、`clear` 清除记忆、`trace` 查看追踪。

## REST API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web UI 页面 |
| `/stream` | POST | SSE 流式聊天 |
| `/chat` | POST | 非流式聊天 |
| `/confirm` | POST | 确认上架（interrupt 恢复） |
| `/memory` | GET/DELETE | 查看/清除长期记忆 |
| `/books` | GET | 查看书库 |
| `/history` | GET | 会话历史列表 |
| `/history/{id}` | GET/DELETE | 查看/删除指定会话 |
| `/workflows` | GET | 可用工作流列表 |
| `/skills` | GET | 已安装技能列表 |
| `/trace` | GET | 追踪历史 |
| `/graph/invoke` | POST | LangServe 标准调用 |
| `/graph/stream` | POST | LangServe 标准流式 |

## 技术栈

- **框架**：LangGraph（图编排）、LangChain（工具/消息）、LangServe（API 标准化）
- **Web**：FastAPI + SSE（流式输出） + Jinja2 模板
- **LLM**：ChatOpenAI 兼容接口（基础模型 deepseek-v4-pro，默认路由 deepseek-chat 以规避 thinking 模型多轮工具调用问题）
- **向量存储**：Milvus（可选）/ 自研 TF-IDF
- **短/长期记忆**：Redis（短期，7 天 TTL）+ JSON/RAG 向量（长期）
- **容器化**：Docker Compose（Milvus 集群）
