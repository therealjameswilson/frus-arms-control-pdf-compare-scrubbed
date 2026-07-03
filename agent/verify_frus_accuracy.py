#!/usr/bin/env python3
"""Verify a generated FRUS draft against a benchmark text."""

from __future__ import annotations

import argparse
import difflib
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = REPO_ROOT / "assets" / "data" / "frus-pdf-compare.json"


def display_path(path_value: str | Path) -> str:
    path = Path(path_value).expanduser()
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def compact_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_frus_html(fragment: str) -> str:
    text = fragment or ""
    text = re.sub(r'<div class="footnotes".*', " ", text, flags=re.I | re.S)
    text = re.sub(r'<span class="frus-page-break">.*?</span>', " ", text, flags=re.I | re.S)
    text = re.sub(r'<a href="#d\d+fn\d+"[^>]*><sup>\d+</sup></a>', " ", text, flags=re.I)
    text = re.sub(r"<sup>\d+</sup>", " ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"</(p|div|li|h[1-6]|ul|ol|table|tr|td|th)>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return compact_ws(html.unescape(text))


def normalize_for_tokens(value: str) -> list[str]:
    text = html.unescape(value or "").lower()
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [token for token in text.split() if len(token) > 1 and not token.isdigit()]


def normalize_for_chars(value: str) -> str:
    text = html.unescape(value or "").lower()
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return compact_ws(text)


def bag_overlap(left: list[str], right: list[str]) -> int:
    return sum((Counter(left) & Counter(right)).values())


def phrase_coverage(benchmark_tokens: list[str], candidate_norm: str, *, n: int = 8, stride: int = 8) -> tuple[float, int, int]:
    phrases = []
    for start in range(0, max(0, len(benchmark_tokens) - n + 1), stride):
        phrase = " ".join(benchmark_tokens[start : start + n])
        if len(phrase) >= 20:
            phrases.append(phrase)
    if not phrases:
        return 0.0, 0, 0
    hits = sum(1 for phrase in phrases if phrase in candidate_norm)
    return hits / len(phrases), hits, len(phrases)


def read_candidate(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix == ".json":
        data = json.loads(text)
        return data.get("draft_body", "")
    return text


def read_benchmark(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.benchmark_file:
        return Path(args.benchmark_file).read_text(encoding="utf-8", errors="ignore"), {"source": args.benchmark_file}
    if args.doc_key or args.doc_no:
        payload = json.loads(Path(args.data).read_text(encoding="utf-8"))
        doc_key = args.doc_key
        if args.doc_no:
            doc_key = f"frus1989-92v31-d{args.doc_no}"
        doc = payload["documents"][doc_key]
        return strip_frus_html(doc.get("html", "")), {
            "source": display_path(args.data),
            "doc_key": doc_key,
            "title": doc.get("title"),
            "url": doc.get("url"),
        }
    raise SystemExit("Supply --benchmark-file, --doc-key, or --doc-no")


def verify(args: argparse.Namespace) -> dict[str, Any]:
    benchmark, benchmark_meta = read_benchmark(args)
    candidate = read_candidate(Path(args.candidate))

    benchmark_tokens = normalize_for_tokens(benchmark)
    candidate_tokens = normalize_for_tokens(candidate)
    overlap = bag_overlap(benchmark_tokens, candidate_tokens)
    token_recall = overlap / max(1, len(benchmark_tokens))
    token_precision = overlap / max(1, len(candidate_tokens))

    benchmark_chars = normalize_for_chars(benchmark)
    candidate_chars = normalize_for_chars(candidate)
    char_similarity = difflib.SequenceMatcher(None, benchmark_chars, candidate_chars).ratio()

    candidate_norm = " ".join(candidate_tokens)
    phrase_score, phrase_hits, phrase_total = phrase_coverage(benchmark_tokens, candidate_norm)

    structure_checks = {
        "nonempty_candidate": bool(candidate_tokens),
        "nonempty_benchmark": bool(benchmark_tokens),
    }
    for required in args.require_text or []:
        structure_checks[f"contains:{required}"] = normalize_for_chars(required) in candidate_chars
    structure_passed = all(structure_checks.values())

    passed = (
        token_recall >= args.threshold
        and token_precision >= args.threshold
        and char_similarity >= args.threshold
        and structure_passed
    )
    blockers = []
    if token_recall < args.threshold:
        blockers.append("normalized_token_recall_below_threshold")
    if token_precision < args.threshold:
        blockers.append("normalized_token_precision_below_threshold")
    if char_similarity < args.threshold:
        blockers.append("normalized_character_similarity_below_threshold")
    if not structure_passed:
        blockers.append("structure_required_items_failed")

    return {
        "passed_99_accuracy_gate": passed,
        "threshold": args.threshold,
        "benchmark_available": True,
        "benchmark": benchmark_meta,
        "candidate": display_path(args.candidate),
        "normalized_token_recall": round(token_recall, 6),
        "normalized_token_precision": round(token_precision, 6),
        "normalized_character_similarity": round(char_similarity, 6),
        "phrase_coverage": round(phrase_score, 6),
        "phrase_hits": phrase_hits,
        "phrase_total": phrase_total,
        "structure_required_items_passed": structure_passed,
        "structure_checks": structure_checks,
        "benchmark_token_count": len(benchmark_tokens),
        "candidate_token_count": len(candidate_tokens),
        "blocking_reasons": blockers,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a generated FRUS draft against a benchmark.")
    parser.add_argument("--candidate", required=True, help="Candidate draft text, Markdown, or publication-packet JSON.")
    parser.add_argument("--benchmark-file", help="Plain-text benchmark file.")
    parser.add_argument("--doc-key", help="Benchmark FRUS document key from the comparison JSON.")
    parser.add_argument("--doc-no", help="Benchmark FRUS document number for frus1989-92v31.")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Comparison JSON path.")
    parser.add_argument("--threshold", type=float, default=0.99, help="Required threshold for the 99 percent gate.")
    parser.add_argument("--require-text", action="append", help="Required normalized text fragment in the candidate.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = verify(args)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["passed_99_accuracy_gate"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
