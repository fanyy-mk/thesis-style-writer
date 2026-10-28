#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键自测：验证整个 skill 的脚本链路能跑通。

覆盖：
1. validate_patterns.py —— 规则库结构合法；
2. style_profile.py —— 从 demos/sample-thesis.md 生成画像 JSON/MD；
3. ai_check.py —— AI 味草稿（demos/ai-flavored-draft.md）必须检出阻断项；
4. ai_check.py —— 改写后草稿（demos/rewritten-draft.md）分数必须明显高于 AI 味版；
5. md2docx.py —— 依赖 python-docx；未安装时打印 SKIP 并继续（不视为失败）。

用法（在技能根目录）：
  python scripts/self_test.py
退出码：0 全部通过（或仅 Word 导出被跳过）；1 有失败。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
DEMOS = ROOT / "demos"
PY = sys.executable


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tsw_test_"))
    failures: list[str] = []
    skips: list[str] = []
    checks = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}" + (f"  —— {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    # 1. 规则库校验
    code, out = run([str(SCRIPTS / "validate_patterns.py")])
    check("validate_patterns.py 规则库校验", code == 0, out.strip().splitlines()[-1] if out.strip() else "无输出")

    # 2. 建画像
    profile = tmp / "style-profile.json"
    stats = tmp / "style-profile-stats.md"
    code, out = run([str(SCRIPTS / "style_profile.py"), str(DEMOS / "sample-thesis.md"),
                     "--name", "自测演示样本", "--json", str(profile), "--md", str(stats)])
    ok = code == 0 and profile.exists() and stats.exists()
    detail = ""
    if ok:
        targets = load_json(profile).get("targets", {})
        detail = f"画像含 targets {len(targets)} 项，统计报告 {stats.stat().st_size} 字节"
    check("style_profile.py 生成画像", ok, detail or out.strip().splitlines()[-1] if out.strip() else "无输出")

    # 3. AI 味草稿必须检出阻断项
    flavored = tmp / "check-flavored.json"
    code, out = run([str(SCRIPTS / "ai_check.py"), str(DEMOS / "ai-flavored-draft.md"),
                     "--baseline", str(profile), "--json", str(flavored)])
    flavored_blocking = 0
    flavored_score = -1
    if flavored.exists():
        data = load_json(flavored)
        flavored_blocking = len(data.get("blocking", []))
        flavored_score = data.get("score", -1)
    ok = flavored.exists() and flavored_blocking > 0
    check("ai_check.py 检出 AI 味草稿阻断项", ok,
          f"阻断项 {flavored_blocking} 个，分数 {flavored_score}" if flavored.exists() else "未生成报告")

    # 4. 改写草稿分数应明显更高
    clean = tmp / "check-clean.json"
    code, out = run([str(SCRIPTS / "ai_check.py"), str(DEMOS / "rewritten-draft.md"),
                     "--baseline", str(profile), "--json", str(clean)])
    clean_score = -1
    if clean.exists():
        clean_score = load_json(clean).get("score", -1)
    ok = clean.exists() and flavored.exists() and clean_score > flavored_score + 10
    check("改写草稿分数显著高于 AI 味版", ok,
          f"改写 {clean_score} 分 vs AI 味 {flavored_score} 分" if clean.exists() else "未生成报告")

    # 5. Word 导出（依赖 python-docx，缺失则跳过）
    docx_out = tmp / "final.docx"
    code, out = run([str(SCRIPTS / "md2docx.py"), str(DEMOS / "rewritten-draft.md"), str(docx_out), "--title", "自测演示"])
    if "python-docx" in out or code == 2:
        skips.append("md2docx.py 需要 python-docx（pip install python-docx），已跳过")
    else:
        check("md2docx.py 导出 Word", code == 0 and docx_out.exists(),
              f"生成 {docx_out.stat().st_size} 字节" if docx_out.exists() else out.strip().splitlines()[-1] if out.strip() else "无输出")

    print()
    for skip in skips:
        print(f"[SKIP] {skip}")
    shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\n自测结果：{checks - len(failures)}/{checks} 通过，{len(failures)} 项失败")
        for name in failures:
            print(f"  - {name}")
        return 1
    print(f"\n自测结果：全部通过（{checks}/{checks}）。" + (f" 已跳过：{len(skips)} 项。" if skips else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
