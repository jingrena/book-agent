"""输入/输出护栏"""

import re

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+(instructions|prompts)",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?\s*:",
    r"忽略\s*(之前|以上|所有).*(指令|提示)",
    r"你现在是",
    r"新指令\s*[：:]",
    r"请(忽略|忘记)(之前|以上)",
]

_SENSITIVE_PATTERNS = [
    (r'(api[_-]?key\s*[=:]\s*)["\']?\w{8,}', r'\1[API_KEY已脱敏]'),
    (r'(password\s*[=:]\s*)["\']?\S+', r'\1[PASSWORD已脱敏]'),
    (r'(\d{6})(\d{4})(\d{4})', r'\1****\3'),
    (r'(1[3-9]\d)\d{4}(\d{4})', r'\1****\2'),
]


def guard_input(text: str) -> tuple:
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "检测到潜在的提示注入攻击"
    if len(text) > 2000:
        return False, "输入过长（超过2000字符）"
    return True, ""


def guard_output(text: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
