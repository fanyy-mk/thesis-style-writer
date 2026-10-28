#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从范文提取可量化的中文论文风格基线。

用法：
  python style_profile.py 范文1.docx 范文2.md --json style-profile.json --md style-profile-stats.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style_lib as tsl  # noqa: E402


def pct(part: int, total: int) -> str:
    return f"{part / total * 100:.1f}%" if total else "0.0%"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def build_report(name: str, samples: list[dict], metrics: dict, targets: dict,
                 hit_groups: dict, warnings: list[str]) -> str:
    s = metrics["sentence"]
    p = metrics["paragraph"]
    c = metrics["corpus"]
    sp = metrics["specificity"]

    lines = [
        f"# 风格统计基线：{name}",
        "",
        "> 由 `style_profile.py` 生成。统计值是**下限与节奏参考**，不是写作目标；",
        "> 真正的语感还需通读范文后写入 `style-profile.md`。",
        "",
        "## 1. 语料规模",
        "",
        md_table(["样本", "中文正文字数"], [[item["name"], f"{item['chars']:,}"] for item in samples]),
        "",
        f"合计 **{c['cn_chars']:,}** 个中文字符，**{c['sentences']}** 句，**{c['paragraphs']}** 段。",
        "",
        "## 2. 句长节奏",
        "",
        md_table(["指标", "数值"], [
            ["平均句长", f"{s['mean']} 字"],
            ["标准差", f"{s['std']} 字"],
            ["P10 / P50 / P90", f"{s['p10']} / {s['p50']} / {s['p90']} 字"],
            ["最短 / 最长", f"{s['min']} / {s['max']} 字"],
            ["短句（≤15 字）占比", pct(round(s['short_ratio'] * c['sentences']), c['sentences'])],
            ["长句（≥50 字）占比", pct(round(s['long_ratio'] * c['sentences']), c['sentences'])],
            ["建议标准差下限", f"{targets['sentence_std_floor']} 字"],
            ["建议平均句长区间", f"{s['mean'] - targets['sentence_mean_tolerance']:.1f}–{s['mean'] + targets['sentence_mean_tolerance']:.1f} 字"],
        ]),
        "",
        md_table(["句长区间", "句数", "占比"],
                 [[key, str(value), pct(value, c['sentences'])] for key, value in s["buckets"].items()]),
        "",
        "## 3. 段落节奏",
        "",
        md_table(["指标", "数值"], [
            ["平均段长", f"{p['mean']} 字"],
            ["段长标准差", f"{p['std']} 字"],
            ["段长变异系数 CV", f"{p['cv']}"],
            ["段长 P10 / P90", f"{p['p10']} / {p['p90']} 字"],
            ["每段句数 均值 / 标准差", f"{p['sent_per_para_mean']} / {p['sent_per_para_std']}"],
            ["建议 CV 下限", f"{targets['paragraph_cv_floor']}"],
        ]),
        "",
        "## 4. 标点密度（每千字）",
        "",
        md_table(["标点", "频次"], [[mark, str(value)] for mark, value in
                                   sorted(metrics["punctuation_per_1000"].items(), key=lambda x: -x[1]) if value]),
        "",
        "## 5. 连接词（每千字，仅列出现过的）",
        "",
        md_table(["连接词", "每千字"], [[word, str(value)] for word, value in
                                    sorted(metrics["connectives_per_1000"].items(), key=lambda x: -x[1])[:15]]),
        "",
        "## 6. 人称、限定与强度",
        "",
        md_table(["类别", "每千字频次"], [
            ["人称", "；".join(f"{k} {v}" for k, v in metrics["person_per_1000"].items()) or "无"],
            ["限定语", "；".join(f"{k} {v}" for k, v in list(metrics["hedges_per_1000"].items())[:8]) or "无"],
            ["强度/评价词", "；".join(f"{k} {v}" for k, v in list(metrics["intensity_per_1000"].items())[:10]) or "无"],
        ]),
        "",
        "## 7. 具体性",
        "",
        md_table(["指标", "每千字", "说明"], [
            ["数字/百分比", f"{sp['digits_per_1000']}", "实验、参数、版本、样本量"],
            ["文献引用标记", f"{sp['citations_per_1000']}", "[1] 或（作者，年份）"],
            ["英文/术语 token", f"{sp['latin_per_1000']}", "技术名词、缩写、代码标识"],
        ]),
        "",
        "## 8. 句首分布",
        "",
        md_table(["句首二字", "次数"], [[item["text"], str(item["count"])] for item in metrics["openers"][:10]]),
        "",
        "## 9. 高频四字片段（≥3 次）",
        "",
        md_table(["片段", "次数"], [[item["text"], str(item["count"])] for item in metrics["ngrams"]["top"][:12]]) or "无",
        "",
        f"重复四字片段占比：**{metrics['ngrams']['repeated_share']:.2%}**（越低说明用词越不套路）。",
        "",
        "## 10. 样本 AI 味自查",
        "",
    ]

    for key, label in (("hard", "A 级硬禁命中"), ("quota", "B 级配额词"), ("warning", "C 级结构告警")):
        group = hit_groups.get(key, [])
        if not group:
            lines.append(f"- {label}：0（样本较干净）")
        else:
            total = sum(item["count"] for item in group)
            detail = "；".join(f"{item['name']}×{item['count']}" for item in group[:8])
            lines.append(f"- {label}：{total} 处（{detail}）")
    lines.extend([
        "",
        "## 11. 建议写作目标（已写入 JSON 的 targets）",
        "",
        md_table(["项", "建议"], [
            ["平均句长", f"{s['mean']} ± {targets['sentence_mean_tolerance']} 字"],
            ["句长标准差", f"≥ {targets['sentence_std_floor']} 字"],
            ["短句占比", f"≥ {targets['short_ratio_min']:.1%}"],
            ["长句占比", f"≤ {targets['long_ratio_max']:.1%}"],
            ["段长 CV", f"≥ {targets['paragraph_cv_floor']}"],
            ["每段句数标准差", f"≥ {targets['sentence_per_para_std_floor']}"],
            ["每千字数字", f"≥ {targets['digits_per_1000_floor']}"],
            ["每千字引用", f"≥ {targets['citations_per_1000_floor']}"],
            ["重复四字片段占比", f"≤ {targets['repeated_ngram_share_ceiling']:.1%}"],
        ]),
        "",
    ])

    if warnings:
        lines.append("## 12. 需要人工判断的警告")
        lines.append("")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="从中文论文范文中提取风格基线")
    parser.add_argument("samples", nargs="+", help="范文文件：.docx / .txt / .md")
    parser.add_argument("--json", dest="json_path", help="输出 JSON 画像")
    parser.add_argument("--md", dest="md_path", help="输出 Markdown 统计报告")
    parser.add_argument("--name", default="样本集", help="画像名称")
    parser.add_argument("--keep-refs", action="store_true", help="保留参考文献部分（默认截断）")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    samples = []
    warnings = []
    per_sample = []
    texts = []
    for path_str in args.samples:
        path = Path(path_str)
        if not path.exists():
            print(f"[跳过] 文件不存在：{path}")
            continue
        try:
            raw = tsl.read_text(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[跳过] 无法读取 {path.name}：{exc}")
            continue
        body = tsl.strip_markdown(tsl.clean_body(raw, keep_refs=args.keep_refs))
        chars = tsl.cn_len(body)
        if chars < 300:
            print(f"[跳过] {path.name} 正文仅 {chars} 字，样本太短")
            continue
        texts.append(body)
        samples.append({"name": path.name, "chars": chars, "path": str(path.resolve())})
        per_sample.append({"name": path.name, "metrics": tsl.compute_metrics(body)})

    if not texts:
        print("没有可用样本。请提供 .docx/.txt/.md 格式的中文论文正文。")
        return 2

    combined = "\n\n".join(texts)
    metrics = tsl.compute_metrics(combined)
    targets = tsl.suggest_targets(metrics)
    patterns = tsl.load_patterns()

    hits = {
        "hard": tsl.find_hits(combined, patterns["hard"]),
        "quota": tsl.quota_report(combined, patterns["quota"], metrics["corpus"]["cn_chars"]),
        "warning": tsl.find_hits(combined, patterns["warning"]),
    }

    hard_total = sum(item["count"] for item in hits["hard"])
    hard_density = hard_total * 1000 / metrics["corpus"]["cn_chars"] if metrics["corpus"]["cn_chars"] else 0

    if len(samples) < 3:
        warnings.append(f"有效样本只有 {len(samples)} 个；建议至少 3 篇同体裁范文，风格判断更稳。")
    if metrics["corpus"]["cn_chars"] < 6000:
        warnings.append("样本文本不足 6000 字，句长/段长统计波动较大，请人工通读校正。")
    if hard_density > 0.8:
        warnings.append(f"样本 A 级硬禁密度 {hard_density:.2f}/千字，偏高；样本可能含 AI 生成文本。"
                        "画像只应采用绝对规范与人工通读结论，不要照抄其套话。")

    means = [item["metrics"]["sentence"]["mean"] for item in per_sample
             if item["metrics"]["corpus"]["sentences"] >= 20]
    if len(means) >= 2 and min(means) > 0:
        ratio = max(means) / min(means)
        if ratio > 1.4:
            warnings.append(f"样本间平均句长差异较大（{min(means):.1f}–{max(means):.1f} 字）；"
                            "请选最接近目标学校/期刊的一篇作为主画像，并在 style-profile.md 注明取舍。")

    report = build_report(args.name, samples, metrics, targets, hits, warnings)

    payload = {
        "name": args.name,
        "version": 1,
        "samples": samples,
        "per_sample": per_sample,
        "corpus": metrics["corpus"],
        "metrics": metrics,
        "targets": targets,
        "ai_hits": hits,
        "hard_density_per_1000": round(hard_density, 3),
        "warnings": warnings,
    }

    if args.json_path:
        Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 JSON 画像：{args.json_path}")
    if args.md_path:
        Path(args.md_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_path).write_text(report, encoding="utf-8")
        print(f"已写入统计报告：{args.md_path}")

    print("\n===== 风格基线摘要 =====")
    print(f"样本 {len(samples)} 篇 / {metrics['corpus']['cn_chars']:,} 字 / "
          f"{metrics['corpus']['sentences']} 句 / {metrics['corpus']['paragraphs']} 段")
    print(f"平均句长 {metrics['sentence']['mean']} 字，标准差 {metrics['sentence']['std']}，"
          f"短句 {metrics['sentence']['short_ratio']:.1%}，长句 {metrics['sentence']['long_ratio']:.1%}")
    print(f"平均段长 {metrics['paragraph']['mean']} 字，CV {metrics['paragraph']['cv']}，"
          f"每段句数 σ={metrics['paragraph']['sent_per_para_std']}")
    print(f"每千字：数字 {metrics['specificity']['digits_per_1000']} / "
          f"引用 {metrics['specificity']['citations_per_1000']} / "
          f"英文 {metrics['specificity']['latin_per_1000']}")
    for warning in warnings:
        print(f"[警告] {warning}")
    print("提示：数字只是下限；请继续通读范文，按 references/style-profile-schema.md 写定性画像。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
