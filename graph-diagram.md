# Book Agent 流程图

## 主图

```mermaid
flowchart TD
    START([用户输入]) --> input_guard

    input_guard{input_guard\n安全检查}
    input_guard -->|通过| quick_reply
    input_guard -->|拦截| output_guard

    quick_reply{quick_reply\n快捷回复}
    quick_reply -->|命中问候语| output_guard
    quick_reply -->|未命中| classify_intent

    classify_intent{classify_intent\n意图分类}
    classify_intent -->|route_type=workflow| workflow_router
    classify_intent -->|route_type=specialists| specialist_chain
    classify_intent -->|route_type=quick_reply| output_guard

    workflow_router[workflow_router\n工作流调度]
    specialist_chain[specialist_chain\n专家链]

    workflow_router --> output_guard
    specialist_chain --> output_guard

    output_guard[output_guard\n输出脱敏] --> memory_update
    memory_update[memory_update\n记忆更新] --> END([返回结果])
```

## 智能推荐子图

> 当 `classify_intent` 识别到"推荐"意图时，`workflow_router` 内部调用此子图。

```mermaid
flowchart TD
    START([workflow_context.query]) --> semantic_search
    semantic_search[semantic_search\n向量检索候选书\ntools/rag.py] --> personalize
    personalize[personalize\n调用 LLM 个性化推荐\nworkflows/recommend.py] --> END([final_reply])
```

## 新书入库子图

```mermaid
flowchart TD
    START([用户输入]) --> extract
    extract[extract_book_info\n正则 + LLM 提取书名作者日期] --> check{信息完整?}
    check -->|缺失字段| ASK([提示用户补充信息])
    check -->|完整| workflow
    workflow[新书入库子图\nworkflows/new_book.py] --> END([final_reply])
```

## 专家链

> 当 `classify_intent` 路由到 `specialists` 时，`specialist_chain` 顺序调用专家。

```mermaid
flowchart LR
    INPUT([用户输入 + 历史消息]) --> S1

    S1["检索员 retriever\n工具: search_books\nsearch_books_semantic"]
    S2["推荐官 recommender\n工具: search_books\nsearch_books_semantic"]
    S3["图书管理员 librarian\n工具: search_books, add_book"]
    S4["通用助手 general\n工具: get_current_time\ncalculate, search_weather"]

    S1 -->|输出作为下一个专家的输入| S2
    S2 --> OUTPUT([final_reply])
    S3 --> OUTPUT
    S4 --> OUTPUT
```

## 一次完整请求的数据流（以"帮我推荐一本书"为例）

```mermaid
sequenceDiagram
    participant U as 用户
    participant CLI as cli.py
    participant G as 主图 graph.py
    participant C as classify_intent
    participant W as 推荐子图
    participant LLM as DeepSeek LLM

    U->>CLI: "帮我推荐一本书"
    CLI->>G: invoke(State)
    G->>G: input_guard → 通过
    G->>G: quick_reply → 未命中
    G->>C: classify_intent
    C->>C: 关键词"推荐"命中
    C-->>G: route_type=workflow, target=智能推荐
    G->>W: workflow_router 启动子图
    W->>W: semantic_search 向量检索候选书
    W->>LLM: personalize 发送 prompt
    LLM-->>W: 推荐文本
    W-->>G: final_reply
    G->>G: output_guard 脱敏
    G->>G: memory_update 提炼记忆
    G-->>CLI: result
    CLI-->>U: 打印推荐结果
```
