"""工作流注册"""

from workflows.new_book import build_new_book_workflow
from workflows.recommend import build_recommend_workflow
from workflows.inventory import build_inventory_workflow
from workflows.borrow import build_borrow_workflow
from workflows.return_book import build_return_workflow


def build_all_workflows(llm):
    """构建所有工作流子图"""
    return {
        "新书入库": {
            "description": "查重 → 智能分类 → 确认上架 → 通知",
            "graph": build_new_book_workflow(llm),
        },
        "智能推荐": {
            "description": "语义检索 → 个性化筛选 → 生成推荐语",
            "graph": build_recommend_workflow(llm),
        },
        "书籍盘点": {
            "description": "统计 → 生成报告",
            "graph": build_inventory_workflow(llm),
        },
        "借书": {
            "description": "检查库存 → 办理借阅 → 通知",
            "graph": build_borrow_workflow(),
        },
        "还书": {
            "description": "查找借阅记录 → 办理归还 → 通知",
            "graph": build_return_workflow(),
        },
    }
