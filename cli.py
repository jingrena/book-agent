"""CLI 入口：命令行交互模式"""

from langchain_core.messages import HumanMessage

from graph import get_graph
from callbacks import tracer
from memory import load_memory, save_memory


def main():
    compiled_graph, app_context = get_graph()
    long_term_memory = app_context["long_term_memory"]

    print(f"\n{'='*60}")
    print("📚 智能图书助手（LangGraph + LangChain 重构版）")
    print("专家团队：检索员 | 推荐官 | 图书管理员 | 通用助手 | 书评家 | 翻译官")
    print("工作流：新书入库 | 智能推荐 | 书籍盘点")
    print("命令：quit 退出 | memory 查看记忆 | clear 清除记忆 | trace 查看追踪历史")
    print(f"{'='*60}")

    session_id = "cli_session"

    while True:
        try:
            user_input = input("\n👤 你：").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if user_input.lower() == "memory":
                if long_term_memory:
                    for m in long_term_memory:
                        print(f"  - {m}")
                else:
                    print("  （暂无长期记忆）")
                continue
            if user_input.lower() == "clear":
                long_term_memory[:] = []
                save_memory([])
                print("  🗑️ 已清除所有记忆")
                continue
            if user_input.lower() == "trace":
                if tracer.history:
                    for t in tracer.history[-5:]:
                        print(f"  📋 {t.user_input[:30]}")
                        print(f"     总耗时：{t.total_duration_ms}ms | 总 Token：{t.total_tokens}")
                else:
                    print("  （暂无追踪记录）")
                continue
            if not user_input:
                continue

            try:
                result = compiled_graph.invoke(
                    {
                        "user_input": user_input,
                        "messages": [HumanMessage(content=user_input)],
                        "session_id": session_id,
                        "workflow_context": {},
                        "specialist_keys": [],
                        "specialist_context": "",
                        "final_reply": "",
                        "input_blocked": False,
                        "block_reason": "",
                        "quick_reply": None,
                    },
                    config={"configurable": {"thread_id": session_id}},
                )
                reply = result.get("final_reply", "")
                if reply:
                    print(f"\n🤖 助手：{reply}")
            except KeyboardInterrupt:
                print("\n\n  ⏹️  当前请求已取消，可以继续对话")
        except KeyboardInterrupt:
            print("\n\n  再按一次 Ctrl+C 退出，或继续输入对话")
            try:
                user_input = input("\n👤 你：").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if not user_input:
                continue
        except EOFError:
            break

    print("\n再见！")


if __name__ == "__main__":
    main()
