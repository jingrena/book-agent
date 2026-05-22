# "帮我推荐一本书" 完整执行追踪

## 主图流转

```mermaid
flowchart TD
    START(["`**用户输入**
    '帮我推荐一本书'`"]) --> input_guard

    input_guard["`**input_guard**
    安全检查通过
    input_blocked = False`"]

    quick_reply["`**quick_reply**
    关键词表未命中
    quick_reply = None`"]

    classify_intent["`**classify_intent**
    '推荐' 关键词命中
    route_type = workflow
    route_target = 智能推荐`"]

    workflow_router["`**workflow_router**
    启动智能推荐子图`"]

    subgraph 智能推荐子图
        s1["`**semantic_search**
        向量检索候选书
        candidates = 《活着》《百年孤独》...`"]
        s2["`**personalize**
        构造 prompt → 调用 LLM
        final_reply = '我推荐《活着》...'`"]
        s1 --> s2
    end

    output_guard["`**output_guard**
    脱敏处理
    messages 追加 AIMessage`"]

    memory_update["`**memory_update**
    异步提炼记忆
    下次对话使用`"]

    END(["`**返回结果**
    '我推荐《活着》...'`"])

    input_guard -->|input_blocked=False| quick_reply
    quick_reply -->|quick_reply=None| classify_intent
    classify_intent -->|route_type=workflow| workflow_router
    workflow_router --> s1
    s2 --> output_guard
    output_guard --> memory_update
    memory_update --> END
```

---

## State 逐步变化

```mermaid
sequenceDiagram
    participant S as State
    participant IG as input_guard
    participant QR as quick_reply
    participant CI as classify_intent
    participant WR as workflow_router
    participant SS as semantic_search
    participant P as personalize (LLM)
    participant OG as output_guard
    participant MU as memory_update

    Note over S: user_input = "帮我推荐一本书"
    Note over S: input_blocked = False
    Note over S: final_reply = ""

    S->>IG: 传入 State
    IG-->>S: input_blocked = False

    S->>QR: 传入 State
    QR-->>S: quick_reply = None

    S->>CI: 传入 State
    CI-->>S: route_type = "workflow"
    CI-->>S: route_target = "智能推荐"

    S->>WR: 传入 State
    WR->>SS: 启动子图
    SS-->>WR: candidates = "《活着》《百年孤独》..."

    WR->>P: candidates + 用户偏好
    Note over P: prompt = "候选书目：...\n请推荐..."
    P-->>WR: final_reply = "我推荐《活着》..."
    WR-->>S: final_reply = "我推荐《活着》..."

    S->>OG: 传入 State
    OG-->>S: messages 追加 AIMessage

    S->>MU: 传入 State
    MU-->>S: 异步写记忆，不更新 State

    Note over S: 返回 final_reply
```

---

## personalize 节点的 Prompt 构造

这是整条链路唯一调用 LLM 的地方（`workflows/recommend.py:51`）：

```
候选书目：
1. 《活着》余华 ...
2. 《百年孤独》马尔克斯 ...
3. ...

用户偏好：（从长期记忆 / RAG 检索，第一次为空）

请从候选中选出最符合用户偏好的 1-2 本，给出推荐理由。用中文回复。
```

LLM 返回推荐文本 → 写入 `final_reply` → 沿图传回主图 → 打印给用户。

---

## 各节点职责一览

| 节点 | 是否调用 LLM | 做什么 |
|------|------------|--------|
| `input_guard` | 否 | 正则检测注入、超长输入 |
| `quick_reply` | 否 | 字典精确匹配问候语 |
| `classify_intent` | 否（关键词命中）/ 是（兜底） | 决定走工作流还是专家链 |
| `semantic_search` | 否 | 向量数据库检索候选书 |
| `personalize` | **是** | 构造 prompt，调 LLM 生成推荐 |
| `output_guard` | 否 | 脱敏，追加消息历史 |
| `memory_update` | 是（异步） | 提炼本轮对话为长期记忆 |
