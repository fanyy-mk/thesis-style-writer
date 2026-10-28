#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""thesis-style-writer 共享分析库（仅标准库）。"""

from __future__ import annotations

import html
import json
import math
import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
SENT_RE = re.compile(r"[^。！？!?]+[。！？!?]?")
REF_HEADING_RE = re.compile(r"^\s*(?:参考文献|References|REFERENCES)\s*$")
TOC_RE = re.compile(r"(?:\.{4,}|…{2,}|·{4,})\s*\d*\s*$")
CITE_RE = re.compile(r"\[\s*\d+(?:\s*[-,，–]\s*\d+)*\s*\]")
DIGIT_RE = re.compile(r"\d+(?:\.\d+)?%?")
LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+#-]*")
PLACEHOLDER_RE = re.compile(r"【[^】\n]{0,40}】|\[待补[^\]]*\]|待补|TODO|[Xx]{2,}%")
LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")

CONNECTIVES = [
    "首先", "其次", "再次", "最后", "此外", "同时", "然而", "因此", "所以",
    "但是", "而且", "并且", "另外", "总之", "综上", "由此可见", "值得注意的是",
    "不难发现", "在此基础上", "一方面", "另一方面", "不仅", "既", "又",
    "进一步", "从而", "进而", "换言之", "也就是说", "使得", "由于", "尽管",
    "虽然", "如果", "随着",
]

PERSON_WORDS = ["本文", "笔者", "我们", "本人", "本研究", "本课题"]
HEDGES = ["可能", "或许", "通常", "往往", "在一定程度", "多数", "尚需", "有待",
          "限于", "仅", "约", "左右", "一般"]
INTENSITY = ["显著", "极大", "大幅", "明显", "充分", "全面", "深入", "有效",
             "良好", "优异", "完善", "重要", "远远", "成倍"]
PUNCTUATION = ["，", "。", "、", "；", "：", "？", "！", "——", "（", "）", "“", "”", "《", "》"]


def cn_len(text: str) -> int:
    return len(CJK_RE.findall(text))


def _per_k(count: int, chars: int) -> float:
    return round(count * 1000.0 / chars, 2) if chars else 0.0


def read_text(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".docx":
        return extract_docx(p)
    if suffix == ".pdf":
        raise ValueError("PDF 请先用 Read 工具分页读取或转换为 txt 后再传入：" + str(p))
    return p.read_text(encoding="utf-8-sig", errors="ignore")


def extract_docx(path: str | Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", "ignore")
    xml = xml.replace("</w:p>", "\n\n")
    xml = xml.replace("</w:tr>", "\n\n")
    xml = xml.replace("<w:br/>", "\n").replace("<w:br />", "\n")
    xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(xml)


def clean_body(text: str, keep_refs: bool = False) -> str:
    """统一换行、去掉目录行，默认在“参考文献”处截断；保留行号。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not keep_refs and REF_HEADING_RE.match(stripped):
            break
        if TOC_RE.search(stripped):
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def strip_markdown(text: str) -> str:
    """去掉 Markdown 标记，尽量保持行数不变，便于报告行号。"""
    text = re.sub(r"```[^\n]*\n.*?```", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text, flags=re.M)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    return text


def get_paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", text)
    paras = []
    for block in blocks:
        merged = re.sub(r"[ \t]+", "", block)
        merged = re.sub(r"\n+", "", merged)
        if cn_len(merged) >= 15:
            paras.append(merged)
    if len(paras) <= 1:
        lines = [re.sub(r"[ \t]+", "", line) for line in text.split("\n")]
        fallback = [line for line in lines if cn_len(line) >= 15]
        if len(fallback) > len(paras):
            paras = fallback
    return paras


def get_sentences(paragraph: str) -> list[str]:
    return [m.group(0).strip() for m in SENT_RE.finditer(paragraph)
            if cn_len(m.group(0)) >= 4]


def _pctl(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_vals[int(k)])
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def _stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "std": 0.0, "min": 0, "max": 0, "p10": 0, "p50": 0, "p90": 0}
    vals = sorted(float(v) for v in values)
    mean = statistics.fmean(vals)
    return {
        "mean": round(mean, 2),
        "std": round(statistics.pstdev(vals), 2),
        "min": round(vals[0], 2),
        "max": round(vals[-1], 2),
        "p10": round(_pctl(vals, 0.10), 2),
        "p50": round(_pctl(vals, 0.50), 2),
        "p90": round(_pctl(vals, 0.90), 2),
    }


def cn_prefix(text: str, n: int = 2) -> str:
    chars = CJK_RE.findall(text)
    return "".join(chars[:n])


def compute_metrics(text: str) -> dict:
    text = clean_body(text)
    paras = get_paragraphs(text)
    sents: list[str] = []
    sent_counts = []
    for para in paras:
        current = get_sentences(para)
        sent_counts.append(len(current))
        sents.extend(current)

    chars = cn_len("\n".join(paras))
    prose = "\n".join(paras)
    slens = [cn_len(s) for s in sents]
    plens = [cn_len(p) for p in paras]

    sentence_stats = _stats(slens)
    buckets = {"1-10": 0, "11-20": 0, "21-30": 0, "31-40": 0, "41-50": 0, "51-70": 0, "71+": 0}
    for length in slens:
        if length <= 10:
            buckets["1-10"] += 1
        elif length <= 20:
            buckets["11-20"] += 1
        elif length <= 30:
            buckets["21-30"] += 1
        elif length <= 40:
            buckets["31-40"] += 1
        elif length <= 50:
            buckets["41-50"] += 1
        elif length <= 70:
            buckets["51-70"] += 1
        else:
            buckets["71+"] += 1
    short_ratio = round(sum(1 for x in slens if x <= 15) / len(slens), 3) if slens else 0.0
    long_ratio = round(sum(1 for x in slens if x >= 50) / len(slens), 3) if slens else 0.0

    paragraph_stats = _stats(plens)
    pmean = paragraph_stats["mean"]
    pcv = round(paragraph_stats["std"] / pmean, 3) if pmean else 0.0
    paragraph_stats["cv"] = pcv
    paragraph_stats["sent_per_para_mean"] = round(statistics.fmean(sent_counts), 2) if sent_counts else 0.0
    paragraph_stats["sent_per_para_std"] = round(statistics.pstdev(sent_counts), 2) if len(sent_counts) > 1 else 0.0

    punct = {mark: _per_k(prose.count(mark), chars) for mark in PUNCTUATION}
    connective_counts = {word: prose.count(word) for word in CONNECTIVES}
    person_counts = {word: prose.count(word) for word in PERSON_WORDS}
    hedge_counts = {word: prose.count(word) for word in HEDGES}
    intensity_counts = {word: prose.count(word) for word in INTENSITY}

    openers = Counter(cn_prefix(s, 2) for s in sents if cn_prefix(s, 2))
    ngram_counter: Counter[str] = Counter()
    ngram_total = 0
    for sentence in sents:
        seq = "".join(CJK_RE.findall(sentence))
        for i in range(len(seq) - 3):
            ngram_counter[seq[i:i + 4]] += 1
            ngram_total += 1
    repeated_tokens = sum(count for count in ngram_counter.values() if count >= 3)
    repeated_share = round(repeated_tokens / ngram_total, 4) if ngram_total else 0.0
    top_ngrams = [{"text": gram, "count": count}
                  for gram, count in ngram_counter.most_common(60) if count >= 3][:12]

    return {
        "corpus": {
            "cn_chars": chars,
            "sentences": len(sents),
            "paragraphs": len(paras),
            "approx_words": chars,
        },
        "sentence": {
            **sentence_stats,
            "buckets": buckets,
            "short_ratio": short_ratio,
            "long_ratio": long_ratio,
        },
        "paragraph": paragraph_stats,
        "punctuation_per_1000": punct,
        "connectives_per_1000": {w: _per_k(c, chars) for w, c in connective_counts.items() if c},
        "person_per_1000": {w: _per_k(c, chars) for w, c in person_counts.items() if c},
        "hedges_per_1000": {w: _per_k(c, chars) for w, c in hedge_counts.items() if c},
        "intensity_per_1000": {w: _per_k(c, chars) for w, c in intensity_counts.items() if c},
        "specificity": {
            "digits_per_1000": _per_k(len(DIGIT_RE.findall(prose)), chars),
            "citations_per_1000": _per_k(len(CITE_RE.findall(prose)), chars),
            "latin_per_1000": _per_k(len(LATIN_RE.findall(prose)), chars),
        },
        "openers": [{"text": w, "count": c} for w, c in openers.most_common(12)],
        "ngrams": {"repeated_share": repeated_share, "top": top_ngrams},
        "sentinel": {
            "em_dash": prose.count("——"),
            "lists": len(LIST_LINE_RE.findall(prose)),
        },
    }


def suggest_targets(metrics: dict) -> dict:
    s = metrics["sentence"]
    p = metrics["paragraph"]
    sp = metrics["specificity"]
    return {
        "sentence_mean": s["mean"],
        "sentence_mean_tolerance": round(max(4.0, s["mean"] * 0.18), 1),
        "sentence_std_floor": round(max(8.0, s["std"] * 0.7), 1),
        "short_ratio_min": round(max(0.02, s["short_ratio"] * 0.6), 3),
        "long_ratio_max": round(min(0.55, s["long_ratio"] * 1.6 + 0.05), 3),
        "paragraph_mean": p["mean"],
        "paragraph_cv_floor": round(max(0.13, min(0.20, p["cv"] * 0.7)), 3),
        "sentence_per_para_std_floor": round(max(0.6, p["sent_per_para_std"] * 0.6), 2),
        "digits_per_1000_floor": round(max(2.0, min(12.0, sp["digits_per_1000"] * 0.4)), 1),
        "citations_per_1000_floor": round(max(0.4, min(3.0, sp["citations_per_1000"] * 0.55)), 1),
        "repeated_ngram_share_ceiling": round(max(0.12, metrics["ngrams"]["repeated_share"] * 1.4), 3),
    }


def load_patterns(path: str | Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).with_name("ai_patterns.json")
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_hits(text: str, items: list[dict], cap: int = 60) -> list[dict]:
    results = []
    for item in items:
        regex = re.compile(item["pattern"])
        hits = []
        for match in regex.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append({"match": match.group(0)[:60], "line": line})
            if len(hits) >= cap:
                break
        if hits:
            results.append({
                "id": item["id"],
                "name": item["name"],
                "count": len(hits),
                "hits": hits,
                "fix": item.get("fix") or item.get("note", ""),
            })
    results.sort(key=lambda x: (-x["count"], x["id"]))
    return results


def quota_report(text: str, items: list[dict], chars: int, cap: int = 400) -> list[dict]:
    results = []
    for item in items:
        count = len(re.findall(item["pattern"], text))
        if count == 0:
            continue
        allowed = max(float(item.get("min_allow", 1.0)), float(item["limit"]) * chars / 1000.0)
        allowed = round(allowed, 2)
        results.append({
            "id": item["id"],
            "name": item["name"],
            "count": count,
            "allowed": allowed,
            "excess": round(max(0.0, count - allowed), 2),
            "note": item.get("note", ""),
        })
    results.sort(key=lambda x: (-x["excess"], -x["count"]))
    return results


def find_placeholders(text: str) -> list[dict]:
    out = []
    for match in PLACEHOLDER_RE.finditer(text):
        out.append({
            "match": match.group(0)[:60],
            "line": text.count("\n", 0, match.start()) + 1,
        })
    return out


def markdown_list_lines(raw: str) -> list[dict]:
    out = []
    for idx, line in enumerate(raw.split("\n"), start=1):
        if LIST_LINE_RE.match(line):
            out.append({"line": idx, "text": line.strip()[:60]})
    return out


def mechanical_enumeration(paragraphs: list[str]) -> list[dict]:
    markers = ["首先", "其次", "再次", "最后"]
    out = []
    for para in paragraphs:
        found = [m for m in markers if m in para]
        if len(found) >= 2:
            out.append({"markers": found, "excerpt": para[:60]})
    return out


def vague_citations(sentences: list[str]) -> list[dict]:
    cues = ["研究表明", "研究发现", "已有研究", "相关研究", "学者认为", "学者们认为", "文献指出"]
    out = []
    for sentence in sentences:
        if any(cue in sentence for cue in cues) and not CITE_RE.search(sentence) and "（20" not in sentence:
            out.append({"excerpt": sentence[:80]})
    return out


def intensity_without_data(sentences: list[str]) -> list[dict]:
    cues = ["显著", "大幅", "明显", "极大", "远远", "成倍"]
    out = []
    for sentence in sentences:
        if any(cue in sentence for cue in cues) and not DIGIT_RE.search(sentence):
            out.append({"excerpt": sentence[:80]})
    return out


def specific_info_missing(paragraphs: list[str]) -> list[dict]:
    out = []
    for para in paragraphs:
        if cn_len(para) < 90:
            continue
        has_digit = bool(DIGIT_RE.search(para))
        has_cite = bool(CITE_RE.search(para))
        has_latin = len(LATIN_RE.findall(para)) >= 2
        if not (has_digit or has_cite or has_latin):
            out.append({"excerpt": para[:80], "chars": cn_len(para)})
    return out


def empty_transitions(sentences: list[str]) -> list[dict]:
    starters = ["因此", "所以", "同时", "此外", "总之", "由此可见", "综上所述", "在此基础上"]
    out = []
    for sentence in sentences:
        if cn_len(sentence) <= 12 and any(sentence.startswith(word) for word in starters):
            out.append({"excerpt": sentence[:40]})
    return out


def duplicate_sentences(sentences: list[str]) -> list[dict]:
    seen: Counter[str] = Counter()
    for sentence in sentences:
        key = re.sub(r"\s+", "", sentence)
        if cn_len(key) >= 12:
            seen[key] += 1
    return [{"excerpt": s[:80], "count": c} for s, c in seen.items() if c >= 2]


def repeated_openers(sentences: list[str], n: int = 4, threshold: int = 3) -> list[dict]:
    counter = Counter(cn_prefix(s, n) for s in sentences if cn_len(s) >= n)
    return [{"opener": w, "count": c} for w, c in counter.most_common(8) if c >= threshold]


def flatten_sentences(paragraphs: list[str]) -> list[str]:
    return [sentence for para in paragraphs for sentence in get_sentences(para)]
