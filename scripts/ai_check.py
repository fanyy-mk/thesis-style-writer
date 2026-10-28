#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文学位论文草稿的“去 AI 味”门禁检查。

用法：
  python ai_check.py draft/ch1.md --baseline thesis/style-profile.json --json report.json
退出码：0 通过；1 未通过（存在阻断项或分数低于阈值）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import thesis_style_lib as tsl  # noqa: E402


def fmt_lines(hits: list[dict], limit: int = 6) -> str:
    lines = [str(item["line"]) for item in hits[:limit]]
    suffix = " 等" if len(hits) > limit else ""
    return "、".join(lines) + suffix


def load_baseline(path: str | None) -> dict:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("targets") or data


def run_check(path: Path, baseline: dict, min_score: int) -> dict:
    raw = tsl.read_text(path)
    body = tsl.clean_body(raw)
    analysis = tsl.strip_markdown(body)
    metrics = tsl.compute_metrics(analysis)
    chars = metrics["corpus"]["cn_chars"]
    paras = tsl.get_paragraphs(analysis)
    sents = tsl.flatten_sentences(paras)

    if chars < 150:
        return {
            "file": str(path), "score": 0, "pass": False,
            "blocking": ["正文不足 150 个中文字符，无法评估。"],
            "warnings": [], "metrics": metrics,
        }

    patterns = tsl.load_patterns()
    hard = tsl.find_hits(analysis, patterns["hard"])
    quota = tsl.quota_report(analysis, patterns["quota"], chars)
    pattern_warnings = tsl.find_hits(analysis, patterns["warning"])

    blocking: list[str] = []
    warnings: list[str] = []
    penalties = {"hard": 0.0, "quota": 0.0, "pattern": 0.0, "rhythm": 0.0,
                 "specificity": 0.0, "structure": 0.0}
    score = 100.0

    # ---------- A 级硬禁 ----------
    for item in hard:
        blocking.append(f"[{item['id']}] {item['name']} ×{item['count']}（第 {fmt_lines(item['hits'])} 行）")
    penalties["hard"] = min(60.0, 12.0 * len(hard))

    # ---------- B 级配额 ----------
    for item in quota:
        if item["excess"] <= 0:
            continue
        allowed = item["allowed"]
        blocking_limit = max(2.0, allowed)
        message = (f"[{item['id']}] {item['name']}：{item['count']} 次 / 允许 {allowed:g} 次"
                   f"（超出 {item['excess']:g}）")
        if item["excess"] >= blocking_limit:
            blocking.append(message)
    total_excess = sum(max(0.0, item["excess"]) for item in quota)
    penalties["quota"] = min(24.0, 4.0 * total_excess)

    # ---------- C 级词句告警 ----------
    penalties["pattern"] = min(15.0, 1.5 * sum(item["count"] for item in pattern_warnings))

    # ---------- 节奏 ----------
    s = metrics["sentence"]
    p = metrics["paragraph"]
    n_sent = metrics["corpus"]["sentences"]

    base_mean = baseline.get("sentence_mean")
    tolerance = baseline.get("sentence_mean_tolerance", 5.0)
    if base_mean and n_sent >= 20:
        if abs(s["mean"] - base_mean) > tolerance:
            warnings.append(f"平均句长 {s['mean']} 字，偏离画像 {base_mean} ±{tolerance} 字")
            penalties["rhythm"] += 6

    if n_sent >= 20:
        std_floor = max(8.0, float(baseline.get("sentence_std_floor", 8.0)))
        if s["std"] < 8.0:
            blocking.append(f"句长过于均匀：标准差 {s['std']} < 8（画像下限 {std_floor}）")
            penalties["rhythm"] += 15
        elif s["std"] < std_floor:
            warnings.append(f"句长标准差 {s['std']}，低于画像下限 {std_floor}")
            penalties["rhythm"] += 8

        if s["short_ratio"] == 0:
            warnings.append("没有 15 字以内的短句，节奏单一")
            penalties["rhythm"] += 6
        else:
            short_floor = float(baseline.get("short_ratio_min", 0.02))
            if baseline and s["short_ratio"] < short_floor * 0.5:
                warnings.append(f"短句占比 {s['short_ratio']:.1%}，低于画像下限 {short_floor:.1%}")
                penalties["rhythm"] += 5

        abs_long_ceiling = float(baseline.get("long_ratio_max", 0.55))
        if s["long_ratio"] > abs_long_ceiling:
            warnings.append(f"长句占比 {s['long_ratio']:.1%}，超过上限 {abs_long_ceiling:.1%}")
            penalties["rhythm"] += 5

    if len(paras) >= 3:
        cv_floor = max(0.13, float(baseline.get("paragraph_cv_floor", 0.16)))
        if p["cv"] < 0.13:
            if len(paras) >= 6:
                blocking.append(f"段落长度过于均匀：CV {p['cv']} < 0.13（画像下限 {cv_floor}）")
                penalties["rhythm"] += 12
            else:
                warnings.append(f"段落长度几乎一样（CV {p['cv']}），段落节奏不自然")
                penalties["rhythm"] += 6
        elif p["cv"] < cv_floor:
            warnings.append(f"段落长度 CV {p['cv']}，低于画像下限 {cv_floor}")
            penalties["rhythm"] += 5

    if len(paras) >= 5 and p["sent_per_para_std"] < 0.6 and p["cv"] < 0.2:
        warnings.append(f"每段句数几乎相同（σ={p['sent_per_para_std']}），有明显模板感")
        penalties["rhythm"] += 6
    elif len(paras) >= 8 and p["sent_per_para_std"] < 0.8:
        warnings.append(f"每段句数过于一致（σ={p['sent_per_para_std']}），有明显模板感")
        penalties["rhythm"] += 6

    if n_sent >= 20 and metrics["openers"]:
        top = metrics["openers"][0]
        ratio = top["count"] / n_sent
        if top["count"] >= 4 and ratio > 0.22:
            warnings.append(f"句首重复：{top['count']} 句以“{top['text']}”开头（{ratio:.0%}）")
            penalties["rhythm"] += 6
        for item in tsl.repeated_openers(sents)[:2]:
            warnings.append(f"连续句首“{item['opener']}”出现 {item['count']} 次")
            penalties["rhythm"] += 4

    ceiling = float(baseline.get("repeated_ngram_share_ceiling", 0.12))
    if metrics["ngrams"]["repeated_share"] > ceiling:
        warnings.append(f"重复四字片段占比 {metrics['ngrams']['repeated_share']:.1%}，高于上限 {ceiling:.1%}")
        penalties["rhythm"] += 6

    starters = ("因此", "所以", "同时", "此外", "总之", "由此可见", "综上所述", "在此基础上")
    if sents:
        transition_ratio = sum(1 for sentence in sents if sentence.startswith(starters)) / len(sents)
        if transition_ratio > 0.25:
            warnings.append(f"{transition_ratio:.0%} 的句子以连接词开头，过渡痕迹过重")
            penalties["rhythm"] += 5

    # ---------- 具体性 ----------
    sp = metrics["specificity"]
    digits_floor = float(baseline.get("digits_per_1000_floor", 2.0))
    if chars >= 400:
        if sp["digits_per_1000"] < 1.0:
            blocking.append(f"每千字数字仅 {sp['digits_per_1000']}，几乎没有可核查信息")
            penalties["specificity"] += 15
        elif sp["digits_per_1000"] < digits_floor * 0.7:
            warnings.append(f"每千字数字 {sp['digits_per_1000']}，低于画像下限 {digits_floor}")
            penalties["specificity"] += 8

    cit_floor = float(baseline.get("citations_per_1000_floor", 0.0))
    if cit_floor and sp["citations_per_1000"] < cit_floor * 0.5:
        warnings.append(f"每千字引用 {sp['citations_per_1000']}，明显少于画像的 {cit_floor}")
        penalties["specificity"] += 6

    missing = tsl.specific_info_missing(paras)
    if len(missing) >= 3 and len(missing) / max(1, len(paras)) >= 0.4:
        warnings.append(f"{len(missing)}/{len(paras)} 个长段落没有数字、引用或英文术语")
        penalties["specificity"] += 8

    vague = tsl.vague_citations(sents)
    if vague:
        warnings.append(f"泛化引用 {len(vague)} 处（“研究表明”类但未给文献）：{vague[0]['excerpt'][:40]}…")
        penalties["specificity"] += min(9.0, 3.0 * len(vague))

    intense = tsl.intensity_without_data(sents)
    if intense:
        warnings.append(f"程度词无数据 {len(intense)} 处：{intense[0]['excerpt'][:40]}…")
        penalties["specificity"] += min(9.0, 3.0 * len(intense))

    # ---------- 结构/模板 ----------
    enum_hits = tsl.mechanical_enumeration(paras)
    for item in enum_hits:
        message = f"机械枚举：同段出现 {'/'.join(item['markers'])}——{item['excerpt'][:36]}…"
        if len(item["markers"]) >= 3:
            blocking.append(message)
            penalties["structure"] += 10
        else:
            warnings.append(message)
            penalties["structure"] += 6

    lists = tsl.markdown_list_lines(body)
    if len(lists) >= 3:
        warnings.append(f"正文使用 {len(lists)} 行项目符号/编号列表，学位论文正文应改为段落")
        penalties["structure"] += 4

    empty = tsl.empty_transitions(sents)
    if empty:
        warnings.append(f"空洞过渡句 {len(empty)} 处：{empty[0]['excerpt']}")
        penalties["structure"] += min(6.0, 2.0 * len(empty))

    duplicates = tsl.duplicate_sentences(sents)
    if duplicates:
        warnings.append(f"重复句 {len(duplicates)} 组：{duplicates[0]['excerpt'][:36]}…")
        penalties["structure"] += min(8.0, 4.0 * len(duplicates))

    placeholders = tsl.find_placeholders(body)

    score -= sum(penalties.values())
    score = max(0, min(100, round(score)))
    passed = score >= min_score and not blocking

    return {
        "file": str(path),
        "score": score,
        "pass": passed,
        "min_score": min_score,
        "blocking": blocking,
        "warnings": warnings,
        "penalties": {key: round(value, 1) for key, value in penalties.items()},
        "metrics": metrics,
        "hard_hits": hard,
        "quota": quota,
        "pattern_warnings": pattern_warnings,
        "placeholders": placeholders,
        "list_lines": lists,
        "vague_citations": vague,
        "intensity_without_data": intense,
        "missing_specifics": missing,
        "mechanical_enumeration": enum_hits,
        "duplicate_sentences": duplicates,
    }


def render(result: dict) -> str:
    m = result.get("metrics", {})
    c = m.get("corpus", {})
    s = m.get("sentence", {})
    p = m.get("paragraph", {})
    sp = m.get("specificity", {})
    lines = [
        "==== 去 AI 味门禁报告 ====",
        f"文件：{result['file']}",
    ]
    if c:
        lines.append(f"规模：{c.get('cn_chars', 0):,} 字 / {c.get('sentences', 0)} 句 / {c.get('paragraphs', 0)} 段")

    verdict = "通过" if result["pass"] else "未通过，需改写后复检"
    lines.append(f"总分：{result['score']}/100（阈值 {result.get('min_score', 85)}）  结论：{verdict}")
    lines.append("")

    if result.get("blocking"):
        lines.append(f"阻断项（{len(result['blocking'])}）")
        lines.extend(f"  - {item}" for item in result["blocking"])
        lines.append("")

    if result.get("quota"):
        lines.append("配额用量")
        for item in result["quota"]:
            mark = "!" if item["excess"] > 0 else "ok"
            lines.append(f"  [{mark}] {item['name']}：{item['count']} 次 / 允许 {item['allowed']:g}"
                         f"（超出 {item['excess']:g}）")
        lines.append("")

    if result.get("pattern_warnings"):
        lines.append("词句告警")
        for item in result["pattern_warnings"]:
            lines.append(f"  - [{item['id']}] {item['name']} ×{item['count']}"
                         f"（第 {', '.join(str(h['line']) for h in item['hits'][:5])} 行）")
        lines.append("")

    if s:
        lines.append("节奏数据")
        lines.append(f"  平均句长 {s.get('mean')} / 标准差 {s.get('std')} / "
                     f"短句 {s.get('short_ratio', 0):.1%} / 长句 {s.get('long_ratio', 0):.1%}")
        lines.append(f"  平均段长 {p.get('mean')} / CV {p.get('cv')} / 每段句数 σ {p.get('sent_per_para_std')}")
        if sp:
            lines.append(f"  每千字：数字 {sp.get('digits_per_1000')} / 引用 {sp.get('citations_per_1000')} / "
                         f"英文术语 {sp.get('latin_per_1000')}")
        lines.append("")

    if result.get("warnings"):
        lines.append(f"其他告警（{len(result['warnings'])}）")
        lines.extend(f"  - {item}" for item in result["warnings"])
        lines.append("")

    if result.get("placeholders"):
        lines.append(f"待补占位符（{len(result['placeholders'])}）——交付前必须补齐或删除")
        lines.append("  " + "、".join(f"第 {item['line']} 行 {item['match']}" for item in result["placeholders"][:10]))
        lines.append("")

    if not result["pass"]:
        lines.append("优先修改顺序")
        step = 1
        for item in result.get("hard_hits", [])[:3]:
            first = item["hits"][0]
            lines.append(f"  {step}) 删/改「{first['match']}」：{item['fix']}")
            step += 1
        if result.get("blocking"):
            lines.append(f"  {step}) 先清阻断项，再处理配额与节奏；最后补具体信息。")
        lines.append("")

    lines.append("说明：脚本只判断可测的“AI 腔”特征，不能替代作者核对事实、数据与引用。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查论文草稿的 AI 腔与节奏")
    parser.add_argument("draft", help="草稿文件：.md / .txt / .docx")
    parser.add_argument("--baseline", help="style_profile.py 生成的 JSON 画像")
    parser.add_argument("--json", dest="json_path", help="输出 JSON 报告")
    parser.add_argument("--min-score", type=int, default=85, help="通过分数线，默认 85")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    path = Path(args.draft)
    if not path.exists():
        print(f"文件不存在：{path}")
        return 2

    try:
        baseline = load_baseline(args.baseline)
    except Exception as exc:  # noqa: BLE001
        print(f"无法读取基线画像：{exc}")
        return 2

    try:
        result = run_check(path, baseline, args.min_score)
    except Exception as exc:  # noqa: BLE001
        print(f"检查失败：{exc}")
        print("请确认文件为 UTF-8 编码的 .md/.txt 或可正常打开的 .docx。")
        return 2
    print(render(result))

    if args.json_path:
        Path(args.json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 报告：{args.json_path}")

    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
