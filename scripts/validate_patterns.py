#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 scripts/ai_patterns.json 的结构与规则合法性。

检查项：
- 顶层必须有 version 与 hard/quota/warning 三个规则组。
- 每组必须是列表；每条规则有必备字段；id 全局唯一且前缀与组名匹配。
- pattern 必须是可编译的正则。
- quota 组必须有 limit（每千字配额）。
- 反例：新增规则后忘了填 fix/note、正则写错、id 重复，本脚本都会报出来。

用法：
  python scripts/validate_patterns.py            # 校验默认规则库
  python scripts/validate_patterns.py <任意.json> # 校验指定文件
退出码：0 通过；1 未通过。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GROUPS = {
    "hard": {"required": ["id", "name", "pattern", "fix"], "prefix": "H"},
    "quota": {"required": ["id", "name", "pattern", "limit"], "prefix": "Q"},
    "warning": {"required": ["id", "name", "pattern", "note"], "prefix": "W"},
}
ALLOWED_TOP_LEVEL = ["version", *GROUPS.keys()]


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"JSON 解析失败：{exc}"]

    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象。"]

    if not data.get("version"):
        errors.append("缺少 version 字段。")

    seen_ids: set[str] = set()
    for group, spec in GROUPS.items():
        items = data.get(group)
        if not isinstance(items, list):
            errors.append(f"缺少规则组「{group}」或它不是数组。")
            continue
        for idx, item in enumerate(items):
            prefix = f"{group}[{idx}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} 必须是对象。")
                continue
            for field in spec["required"]:
                if field not in item or item[field] in (None, ""):
                    errors.append(f"{prefix} 缺少必备字段「{field}」。")
            rule_id = item.get("id", "")
            id_re = rf"^{spec['prefix']}\d{{2}}$"
            if not re.match(id_re, rule_id):
                errors.append(f"{prefix} 的 id「{rule_id}」不符合格式（应为 {spec['prefix']}01 这类两位编号）。")
            elif rule_id in seen_ids:
                errors.append(f"{prefix} 的 id「{rule_id}」重复。")
            else:
                seen_ids.add(rule_id)
            pattern = item.get("pattern", "")
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"{prefix}（{rule_id or '无id'}）正则无法编译：{exc}")

    for group, items in data.items():
        if group in ALLOWED_TOP_LEVEL:
            continue
        errors.append(f"未知顶层字段「{group}」；规则组只能是 {list(GROUPS)}，另有 version。")

    return errors


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "ai_patterns.json"
    if not target.exists():
        print(f"文件不存在：{target}")
        return 2
    errors = validate_file(target)
    if errors:
        print(f"[FAIL] {target}：{len(errors)} 个问题")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"[PASS] {target}：规则结构合法（version={json.loads(target.read_text(encoding='utf-8')).get('version')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
