#!/usr/bin/env python3
"""Build a reviewable FRUS publication packet from one source PDF.

The runner is deliberately conservative. START I training pairs teach the
process model, but the deployment target can be any source PDF with
editor-supplied metadata and page-span evidence. It emits evidence and review
warnings rather than pretending OCR is final publication text.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


AGENT_NAME = "FRUS_PUBLICATION_AGENT"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRAINING_DATA = REPO_ROOT / "assets" / "data" / "frus-pdf-compare.json"
DEFAULT_PROCESS_PROFILE = REPO_ROOT / "agent" / "patterns" / "start_i_publication_process.json"
DEFAULT_CACHE = Path.home() / ".cache" / "frus-publication-agent"
DEFAULT_OUTPUT = Path(tempfile.gettempdir()) / "frus-publication-agent-output"


def compact_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def strip_html(fragment: str) -> str:
    fragment = re.sub(r'<div class="footnotes".*', " ", fragment or "", flags=re.I | re.S)
    fragment = re.sub(r'<span class="frus-page-break">.*?</span>', " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r'<a href="#d\d+fn\d+"[^>]*><sup>\d+</sup></a>', " ", fragment, flags=re.I)
    fragment = re.sub(r"<sup>\d+</sup>", " ", fragment, flags=re.I)
    fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.I)
    fragment = re.sub(r"</(p|div|li|h[1-6]|ul|ol|table|tr|td|th)>", " ", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return compact_ws(html.unescape(fragment))


def normalized_tokens(value: str) -> list[str]:
    text = html.unescape(value or "").lower()
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [token for token in text.split() if len(token) > 1 and not token.isdigit()]


def normalized_chars(value: str) -> str:
    return " ".join(normalized_tokens(value))


def bag_overlap(left: list[str], right: list[str]) -> int:
    return sum((Counter(left) & Counter(right)).values())


def phrase_coverage(benchmark_tokens: list[str], candidate_norm: str, *, n: int = 8, stride: int = 8) -> tuple[float, int, int]:
    phrases = sampled_phrases(benchmark_tokens, n=n, stride=stride)
    if not phrases:
        return 0.0, 0, 0
    hits = sum(1 for phrase in phrases if phrase in candidate_norm)
    return hits / len(phrases), hits, len(phrases)


def sampled_phrases(tokens: list[str], *, n: int = 8, stride: int = 8) -> list[str]:
    phrases = []
    for start in range(0, max(0, len(tokens) - n + 1), stride):
        phrase = " ".join(tokens[start : start + n])
        if len(phrase) >= 20:
            phrases.append(phrase)
    return phrases


def support_gap_report(source_text: str, approved_transcript: str, *, max_items: int = 12) -> dict[str, Any]:
    """Summarize why selected source text does or does not support a transcript."""
    if not approved_transcript:
        return {
            "available": False,
            "sampled_missing_benchmark_phrases": [],
            "sampled_extra_source_phrases": [],
            "top_missing_tokens": [],
            "top_extra_tokens": [],
        }

    source_tokens = normalized_tokens(source_text)
    transcript_tokens = normalized_tokens(approved_transcript)
    source_norm = " ".join(source_tokens)
    transcript_norm = " ".join(transcript_tokens)
    missing_phrases = [
        phrase
        for phrase in sampled_phrases(transcript_tokens)
        if phrase not in source_norm
    ]
    extra_phrases = [
        phrase
        for phrase in sampled_phrases(source_tokens)
        if phrase not in transcript_norm
    ]
    missing_tokens = (Counter(transcript_tokens) - Counter(source_tokens)).most_common(max_items)
    extra_tokens = (Counter(source_tokens) - Counter(transcript_tokens)).most_common(max_items)
    return {
        "available": True,
        "sampled_missing_benchmark_phrase_count": len(missing_phrases),
        "sampled_extra_source_phrase_count": len(extra_phrases),
        "sampled_missing_benchmark_phrases": missing_phrases[:max_items],
        "sampled_extra_source_phrases": extra_phrases[:max_items],
        "top_missing_tokens": [{"token": token, "count": count} for token, count in missing_tokens],
        "top_extra_tokens": [{"token": token, "count": count} for token, count in extra_tokens],
    }


def accuracy_report(candidate: str, benchmark: str, *, threshold: float = 0.99) -> dict[str, Any]:
    if not benchmark:
        return {
            "passed_99_accuracy_gate": False,
            "threshold": threshold,
            "benchmark_available": False,
            "human_certification_required": True,
            "normalized_token_recall": None,
            "normalized_token_precision": None,
            "normalized_character_similarity": None,
            "phrase_coverage": None,
            "structure_required_items_passed": False,
            "blocking_reasons": ["benchmark_text_missing"],
        }

    benchmark_tokens = normalized_tokens(benchmark)
    candidate_tokens = normalized_tokens(candidate)
    overlap = bag_overlap(benchmark_tokens, candidate_tokens)
    token_recall = overlap / max(1, len(benchmark_tokens))
    token_precision = overlap / max(1, len(candidate_tokens))
    char_similarity = difflib.SequenceMatcher(None, normalized_chars(benchmark), normalized_chars(candidate)).ratio()
    phrase_score, phrase_hits, phrase_total = phrase_coverage(benchmark_tokens, " ".join(candidate_tokens))
    structure_passed = bool(benchmark_tokens and candidate_tokens)
    blockers = []
    if token_recall < threshold:
        blockers.append("normalized_token_recall_below_threshold")
    if token_precision < threshold:
        blockers.append("normalized_token_precision_below_threshold")
    if char_similarity < threshold:
        blockers.append("normalized_character_similarity_below_threshold")
    if not structure_passed:
        blockers.append("structure_required_items_failed")

    return {
        "passed_99_accuracy_gate": not blockers,
        "threshold": threshold,
        "benchmark_available": True,
        "human_certification_required": False,
        "normalized_token_recall": round(token_recall, 6),
        "normalized_token_precision": round(token_precision, 6),
        "normalized_character_similarity": round(char_similarity, 6),
        "phrase_coverage": round(phrase_score, 6),
        "phrase_hits": phrase_hits,
        "phrase_total": phrase_total,
        "structure_required_items_passed": structure_passed,
        "benchmark_token_count": len(benchmark_tokens),
        "candidate_token_count": len(candidate_tokens),
        "blocking_reasons": blockers,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"Missing required tool: {name}")
    return found


def parse_page_range(value: str | None) -> list[int] | None:
    if not value:
        return None
    pages: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                raise ValueError(f"Invalid page range: {part}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    return sorted(pages)


def parse_int_list(value: str | None) -> list[int]:
    if not value:
        return []
    items = []
    for part in value.split(","):
        part = part.strip()
        if part:
            items.append(int(part))
    return items


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def select_training_row(payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any] | None:
    rows = payload.get("comparisons", [])
    if args.row_id:
        for row in rows:
            if row.get("id") == args.row_id:
                return row
        raise SystemExit(f"No comparison row with id {args.row_id}")
    if args.doc_key:
        for row in rows:
            if row.get("doc_key") == args.doc_key:
                return row
        raise SystemExit(f"No comparison row with doc_key {args.doc_key}")
    if args.doc_no:
        matches = [row for row in rows if str(row.get("doc_no")) == str(args.doc_no)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit(f"More than one row has doc_no {args.doc_no}; use --row-id")
        raise SystemExit(f"No comparison row with doc_no {args.doc_no}")
    return None


def should_select_training_row(args: argparse.Namespace) -> bool:
    if args.pdf:
        return bool(args.row_id or args.doc_key)
    return bool(args.row_id or args.doc_key or args.doc_no)


def read_optional_text(value: str | None, path_value: str | None) -> str:
    if path_value:
        return Path(path_value).expanduser().read_text(encoding="utf-8")
    return value or ""


def approved_transcript_supported(
    support_report: dict[str, Any],
    *,
    recall_threshold: float,
    phrase_threshold: float,
) -> bool:
    if "passed_source_support_gate" in support_report:
        return bool(support_report["passed_source_support_gate"])
    if not support_report.get("benchmark_available"):
        return False
    recall = support_report.get("normalized_token_recall") or 0.0
    phrase = support_report.get("phrase_coverage") or 0.0
    return recall >= recall_threshold and phrase >= phrase_threshold


def source_support_report(
    source_text: str,
    approved_transcript: str,
    *,
    recall_threshold: float,
    phrase_threshold: float,
) -> dict[str, Any]:
    report = accuracy_report(source_text, approved_transcript, threshold=recall_threshold)
    recall = report.get("normalized_token_recall") or 0.0
    phrase = report.get("phrase_coverage") or 0.0
    blockers = []
    if not report.get("benchmark_available"):
        blockers.append("approved_transcript_missing")
    if recall < recall_threshold:
        blockers.append("source_token_recall_below_threshold")
    if phrase < phrase_threshold:
        blockers.append("source_phrase_coverage_below_threshold")
    report["passed_source_support_gate"] = not blockers
    report["source_support_recall_threshold"] = recall_threshold
    report["source_support_phrase_threshold"] = phrase_threshold
    report["source_support_blocking_reasons"] = blockers
    report["gap_report"] = support_gap_report(source_text, approved_transcript)
    return report


def load_process_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def safe_filename_from_url(url: str) -> str:
    name = Path(urllib.parse.urlparse(url).path).name or "source.pdf"
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{digest}-{name}"


def resolve_pdf(pdf_arg: str, cache_dir: Path) -> tuple[Path, str]:
    if re.match(r"^https?://", pdf_arg):
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest = cache_dir / safe_filename_from_url(pdf_arg)
        if not dest.exists():
            req = urllib.request.Request(pdf_arg, headers={"User-Agent": "FRUS publication agent"})
            with urllib.request.urlopen(req, timeout=180) as response:
                dest.write_bytes(response.read())
        return dest, pdf_arg
    path = Path(pdf_arg).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"PDF not found: {path}")
    return path, str(path)


def pdf_page_count(pdf_path: Path) -> int:
    require_tool("pdfinfo")
    result = run_command(["pdfinfo", str(pdf_path)], timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pdfinfo failed")
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, flags=re.M)
    if not match:
        raise RuntimeError("Could not read page count from pdfinfo")
    return int(match.group(1))


def embedded_text_by_page(pdf_path: Path) -> list[str]:
    require_tool("pdftotext")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "embedded.txt"
        result = run_command(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), str(out)], timeout=180)
        if result.returncode != 0:
            return []
        text = out.read_text(encoding="utf-8", errors="ignore")
    return text.split("\f")


def render_and_ocr_page(pdf_path: Path, page: int, ocr_dir: Path, dpi: int, psm: int) -> str:
    require_tool("pdftoppm")
    require_tool("tesseract")
    variant_dir = ocr_dir / f"dpi-{dpi:04d}-psm-{psm}"
    variant_dir.mkdir(parents=True, exist_ok=True)
    cached = variant_dir / f"page-{page:04d}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8", errors="ignore")

    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / f"page-{page:04d}"
        result = run_command(
            ["pdftoppm", "-r", str(dpi), "-png", "-f", str(page), "-l", str(page), str(pdf_path), str(prefix)],
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"pdftoppm failed on page {page}")
        images = sorted(Path(tmp).glob(f"page-{page:04d}*.png"))
        if not images:
            raise RuntimeError(f"pdftoppm produced no image for page {page}")
        txt_base = Path(tmp) / f"page-{page:04d}-ocr"
        result = run_command(["tesseract", str(images[0]), str(txt_base), "--psm", str(psm)], timeout=240)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"tesseract failed on page {page}")
        text = txt_base.with_suffix(".txt").read_text(encoding="utf-8", errors="ignore")
    cached.write_text(text, encoding="utf-8")
    return text


def get_page_texts(
    pdf_path: Path,
    pages: list[int],
    cache_dir: Path,
    dpi: int,
    psm: int,
) -> tuple[list[dict[str, Any]], bool]:
    embedded = embedded_text_by_page(pdf_path)
    embedded_chars = sum(len(re.sub(r"\s+", "", page)) for page in embedded)
    if embedded_chars > 500:
        page_records = []
        for page in pages:
            text = embedded[page - 1] if page - 1 < len(embedded) else ""
            page_records.append({"page": page, "text": text, "method": "embedded_text"})
        return page_records, False

    digest = sha256_file(pdf_path)[:16]
    ocr_dir = cache_dir / "ocr" / digest
    page_records = []
    for page in pages:
        text = render_and_ocr_page(pdf_path, page, ocr_dir, dpi, psm)
        page_records.append({"page": page, "text": text, "method": "ocr", "ocr_dpi": dpi, "ocr_psm": psm})
    return page_records, True


PAGE_CLASS_PATTERNS: list[tuple[str, list[str]]] = [
    ("administrative_marker", ["administrative marker", "record group/collection", "record group", "folder title", "oa/id number", "container id", "box number"]),
    ("withdrawal_sheet", ["withdrawal/redaction sheet", "withdrawal sheet", "restriction", "foia/sys case", "released in part", "sanitized", "redaction"]),
    ("access_control", ["attached document contains classified", "access list"]),
    ("routing_profile", ["nsc profile", "source data page", "action officer", "routing and transmittal"]),
    ("distribution_record", ["distribution record", "directorate distribution", "external distribution", "distribution list"]),
    (
        "source_document",
        [
            "the white house",
            "department of state",
            "embassy",
            "memorandum for",
            "memorandum from",
            "memorandum of conversation",
            "subject:",
            "telegram",
            "message from",
            "letter from",
            "paper prepared",
            "minutes of",
            "summary of conclusions",
            "national security review",
            "national security directive",
            "national security decision memorandum",
            "presidential directive",
        ],
    ),
]


def classify_page(text: str) -> tuple[str, list[str]]:
    norm = normalize_for_match(text)
    hits: list[str] = []
    for label, cues in PAGE_CLASS_PATTERNS:
        matched = [cue for cue in cues if normalize_for_match(cue) in norm]
        if matched:
            hits.extend(matched[:3])
            return label, hits
    if len(norm) < 30:
        return "blank_or_noise", []
    return "source_document", ["substantial OCR text without administrative cues"]


def source_document_score(page_text: str, model_text: str) -> float:
    if not model_text:
        return 0.0
    page_norm = normalize_for_match(page_text)
    model_norm = normalize_for_match(model_text)
    model_tokens = model_norm.split()
    if not page_norm or not model_tokens:
        return 0.0

    phrase_hits = 0
    phrases = []
    words = model_tokens[:700]
    for start in range(0, max(1, len(words) - 12), 30):
        phrase = " ".join(words[start : start + 12])
        if len(phrase) > 40:
            phrases.append(phrase)
    for phrase in phrases[:24]:
        if phrase in page_norm:
            phrase_hits += 1

    page_tokens = set(page_norm.split())
    model_set = set(model_tokens[:900])
    overlap = len(page_tokens & model_set) / max(1, min(len(page_tokens), len(model_set)))
    return round((phrase_hits * 2.0) + overlap, 3)


def choose_benchmark_span(
    page_records: list[dict[str, Any]],
    model_text: str,
    *,
    max_span_pages: int = 25,
) -> dict[str, Any] | None:
    if not model_text:
        return None
    sorted_records = sorted(page_records, key=lambda record: int(record["page"]))
    if not any(record.get("page_class") == "source_document" for record in sorted_records):
        return None

    best: dict[str, Any] | None = None
    for start in range(len(sorted_records)):
        for end in range(start, min(len(sorted_records), start + max_span_pages)):
            span_records = sorted_records[start : end + 1]
            if not any(record.get("page_class") == "source_document" for record in span_records):
                continue
            candidate_records = [
                {
                    "page": record["page"],
                    "page_class": record.get("page_class"),
                    "text": record.get("text", ""),
                }
                for record in span_records
            ]
            body = clean_body_text(candidate_records)
            report = accuracy_report(body, model_text)
            recall = report.get("normalized_token_recall") or 0.0
            precision = report.get("normalized_token_precision") or 0.0
            char_similarity = report.get("normalized_character_similarity") or 0.0
            # Selection favors balanced recall/precision first. Character
            # similarity remains in diagnostics because OCR order/style can be
            # poor before final transcription.
            if recall + precision == 0:
                f1 = 0.0
            else:
                f1 = (2 * recall * precision) / (recall + precision)
            pages = [record["page"] for record in span_records]
            body_pages = [record["page"] for record in span_records if record.get("page_class") == "source_document"]
            crossed_non_body_pages = [record["page"] for record in span_records if record.get("page_class") != "source_document"]
            selection_score = f1 - (0.01 * len(crossed_non_body_pages)) - (0.001 * max(0, len(pages) - 1))
            candidate = {
                "strategy": "benchmark_guided_contiguous_pdf_span",
                "pages": pages,
                "body_pages": body_pages,
                "crossed_non_body_pages": crossed_non_body_pages,
                "score": round(selection_score, 6),
                "text_match_score": round(f1, 6),
                "normalized_token_recall": recall,
                "normalized_token_precision": precision,
                "normalized_character_similarity": char_similarity,
                "phrase_coverage": report.get("phrase_coverage"),
                "candidate_token_count": report.get("candidate_token_count"),
            }
            if best is None:
                best = candidate
                continue
            if candidate["score"] > best["score"]:
                best = candidate
            elif candidate["score"] == best["score"] and len(candidate["pages"]) < len(best["pages"]):
                best = candidate
    return best


NOISE_LINE_PATTERNS = [
    r"^bush library photocopy$",
    r"^.*library photocopy$",
    r"^.*handwriting$",
    r"^declassified$",
    r"^per e\.?o\.?",
    r"^lpilm\b",
    r"^declassify on:",
    r"^secret$",
    r"^confidential$",
    r"^unclassified upon$",
    r"^removal of classified$",
    r"^attachments$",
    r"^cap\s+\d",
    r"^page\s+\d+\s+of\s+\d+",
]


def repair_ocr_line(line: str) -> str:
    line = line.replace("\u00a0", " ")
    line = line.replace("\u2014", "--").replace("\u2013", "-")
    line = line.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    line = re.sub(r"\s+([,.;:])", r"\1", line)
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def is_noise_line(line: str) -> bool:
    compact = normalize_for_match(line)
    if not compact:
        return True
    for pattern in NOISE_LINE_PATTERNS:
        if re.search(pattern, compact, flags=re.I):
            return True
    return False


def transcript_line_entries(page_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in page_records:
        if record.get("page_class") != "source_document":
            continue
        for source_line_no, raw_line in enumerate(str(record.get("text", "")).splitlines(), start=1):
            line = repair_ocr_line(raw_line)
            if is_noise_line(line):
                continue
            entries.append({
                "page": record.get("page"),
                "source_line_no": source_line_no,
                "text": line,
                "normalized_token_count": len(normalized_tokens(line)),
                "review_flags": [],
            })
    return entries


def clean_body_text(page_records: list[dict[str, Any]]) -> str:
    kept: list[str] = []
    previous_page = None
    for entry in transcript_line_entries(page_records):
        if previous_page is not None and entry.get("page") != previous_page:
            kept.append("")
        kept.append(str(entry.get("text", "")))
        previous_page = entry.get("page")

    text = "\n".join(kept)
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def paragraphs_from_text(text: str) -> list[str]:
    chunks = [compact_ws(chunk) for chunk in re.split(r"\n\s*\n", text or "")]
    return [chunk for chunk in chunks if chunk]


def build_markdown(packet: dict[str, Any]) -> str:
    target = packet["target"]
    lines = [
        f"# {target.get('title') or 'Untitled FRUS Draft'}",
        "",
        f"- Agent: `{packet['agent']}`",
        f"- Run mode: `{packet['run_mode']}`",
        f"- Trained from: {packet.get('training_profile', {}).get('trained_from', 'not recorded')}",
        f"- Source: {packet['source_pdf'].get('source')}",
        f"- Source SHA-256: `{packet['source_pdf'].get('sha256')}`",
        f"- OCR required: `{packet['source_pdf'].get('ocr_required')}`",
        f"- Selected pages: {', '.join(str(p) for p in packet['selected_pages']) or 'not selected'}",
        f"- Body text mode: `{packet.get('body_text_mode')}`",
        "",
        "## Source Note Model",
        "",
        packet.get("source_note_model") or "Source note not supplied.",
        "",
        "## Human Review Warnings",
        "",
    ]
    for warning in packet["human_review_warnings"]:
        lines.append(f"- {warning}")
    lines.extend(["", "## Draft Body", ""])
    lines.append(packet["draft_body"] or "[No body text selected.]")
    lines.extend(["", "## Page Inventory", ""])
    for page in packet["page_inventory"]:
        cues = "; ".join(page.get("cues", []))
        lines.append(f"- Page {page['page']}: `{page['page_class']}`; score `{page['model_match_score']}`; {cues}")
    return "\n".join(lines).rstrip() + "\n"


def build_tei_stub(packet: dict[str, Any]) -> str:
    target = packet["target"]
    doc_no = target.get("doc_no") or "0"
    title = html.escape(target.get("title") or "Untitled FRUS Draft")
    source_note = html.escape(packet.get("source_note_model") or "")
    body = paragraphs_from_text(packet["draft_body"])
    body_xml = "\n".join(f"    <p>{html.escape(p)}</p>" for p in body)
    return textwrap.dedent(
        f"""\
        <div type="document" subtype="historical-document" n="{html.escape(str(doc_no))}" xml:id="d{html.escape(str(doc_no))}">
          <head>{title}<note n="1" type="source">{source_note}</note></head>
        {body_xml}
        </div>
        """
    )


def output_packet(packet: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "publication-packet.json").write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    (output_dir / "draft.md").write_text(build_markdown(packet), encoding="utf-8")
    (output_dir / "draft.xml").write_text(build_tei_stub(packet), encoding="utf-8")
    (output_dir / "page-inventory.json").write_text(json.dumps(packet["page_inventory"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "transcript-lines.json").write_text(json.dumps(packet["transcript_lines"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "accuracy-report.json").write_text(json.dumps(packet["accuracy_report"], indent=2) + "\n", encoding="utf-8")
    (output_dir / "source-support-gaps.json").write_text(
        json.dumps(packet.get("approved_transcript_support", {}).get("report", {}).get("gap_report", {}), indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "review-checklist.md").write_text(build_review_checklist(packet), encoding="utf-8")


def build_review_checklist(packet: dict[str, Any]) -> str:
    report = packet.get("accuracy_report", {})
    lines = [
        "# FRUS Draft Review Checklist",
        "",
        f"- 99% gate passed: `{report.get('passed_99_accuracy_gate')}`",
        f"- Benchmark available: `{report.get('benchmark_available')}`",
        f"- Selected pages: {', '.join(str(p) for p in packet.get('selected_pages', [])) or 'none'}",
        f"- Body text mode: `{packet.get('body_text_mode')}`",
        f"- Transcript lines: {len(packet.get('transcript_lines', []))}",
        "",
        "## Required Human Checks",
        "",
        "- Confirm the selected pages contain one document only.",
        "- Compare `transcript-lines.json` against page images.",
        "- Remove routing/profile/distribution scaffolding from body text.",
        "- Confirm title, opener, source note, attachments, and excisions.",
        "- Re-run `agent/verify_frus_accuracy.py` before claiming 99%.",
        "",
        "## Blocking Reasons",
        "",
    ]
    blockers = report.get("blocking_reasons") or []
    if blockers:
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    else:
        lines.append("- None recorded.")
    support = packet.get("approved_transcript_support", {}).get("report", {})
    support_blockers = support.get("source_support_blocking_reasons") or []
    gap_report = support.get("gap_report") or {}
    lines.extend(["", "## Source Support Gaps", ""])
    if support_blockers:
        lines.append("Source-support blockers:")
        lines.extend(f"- `{blocker}`" for blocker in support_blockers)
    else:
        lines.append("- No source-support blockers recorded.")
    missing_phrases = gap_report.get("sampled_missing_benchmark_phrases") or []
    if missing_phrases:
        lines.extend(["", "Sample benchmark phrases not supported by selected source OCR:"])
        lines.extend(f"- {phrase}" for phrase in missing_phrases[:8])
    extra_phrases = gap_report.get("sampled_extra_source_phrases") or []
    if extra_phrases:
        lines.extend(["", "Sample selected-source OCR phrases outside the approved transcript:"])
        lines.extend(f"- {phrase}" for phrase in extra_phrases[:8])
    return "\n".join(lines).rstrip() + "\n"


def build_training_profile(
    payload: dict[str, Any],
    data_path: Path,
    process_profile_path: Path,
    process_profile: dict[str, Any],
) -> dict[str, Any]:
    return {
        "process_model": process_profile.get("agent") or "FRUS_PUBLICATION_AGENT",
        "trained_from": process_profile.get("trained_from", "START I exact-source PDF/FRUS comparison set"),
        "training_data": str(data_path),
        "training_summary": payload.get("summary", {}),
        "process_profile": str(process_profile_path),
        "universal_deployment": True,
    }


def build_packet(args: argparse.Namespace) -> dict[str, Any]:
    training_data_path = Path(args.training_data)
    payload = load_payload(training_data_path)
    process_profile_path = Path(args.process_profile)
    process_profile = load_process_profile(process_profile_path)
    known_row = select_training_row(payload, args) if should_select_training_row(args) else None
    documents = payload.get("documents", {})

    pdf_source = args.pdf
    target: dict[str, Any] = {
        "volume_id": args.volume_id,
        "doc_no": args.doc_no,
        "doc_key": args.doc_key,
        "title": args.title,
        "frus_url": "",
        "document_type": args.document_type,
        "date": args.date,
        "place": args.place,
        "sender": args.sender,
        "recipient": args.recipient,
        "classification": args.classification,
        "archive_title": args.archive_title,
        "file_unit": args.file_unit,
    }
    source_note = read_optional_text(args.source_note, args.source_note_file)
    model_text = read_optional_text(args.model_text, args.model_text_file)
    approved_transcript = read_optional_text(args.approved_transcript, args.approved_transcript_file)

    if known_row:
        pdf_source = known_row["pdf_url"]
        doc = documents.get(known_row["doc_key"], {})
        target = {
            "volume_id": known_row.get("volume_id"),
            "doc_no": known_row.get("doc_no"),
            "doc_key": known_row.get("doc_key"),
            "title": doc.get("title") or known_row.get("doc_title"),
            "frus_url": doc.get("url") or known_row.get("frus_url"),
            "archive_title": known_row.get("archive_title"),
            "file_unit": known_row.get("archive_title"),
            "match_basis": known_row.get("match_basis"),
        }
        source_note = source_note or doc.get("source_note") or known_row.get("source_note") or ""
        model_text = model_text or strip_html(doc.get("html", ""))
        approved_transcript = approved_transcript or model_text

    if not pdf_source:
        raise SystemExit("Supply --pdf for universal deployment, or select a training row with --doc-no, --doc-key, or --row-id")

    cache_dir = Path(args.cache_dir).expanduser()
    pdf_path, source_label = resolve_pdf(pdf_source, cache_dir / "pdfs")
    page_count = pdf_page_count(pdf_path)
    requested_pages = parse_page_range(args.page_range)
    full_ocr = bool(args.full_ocr)
    if requested_pages is None:
        if full_ocr:
            pages = list(range(1, page_count + 1))
        else:
            pages = list(range(1, min(page_count, args.max_ocr_pages) + 1))
    else:
        pages = [page for page in requested_pages if 1 <= page <= page_count]
    if not pages:
        raise SystemExit("No valid pages selected for OCR/text extraction")

    page_records, ocr_required = get_page_texts(pdf_path, pages, cache_dir, args.ocr_dpi, args.ocr_psm)
    for record in page_records:
        page_class, cues = classify_page(record["text"])
        record["page_class"] = page_class
        record["cues"] = cues
        record["model_match_score"] = source_document_score(record["text"], model_text)
        record["text_preview"] = compact_ws(record["text"])[:500]

    span_selection: dict[str, Any] = {"strategy": "none", "pages": []}
    selected_pages = []
    if requested_pages is not None:
        selected_pages = pages
        span_selection = {"strategy": "editor_supplied_page_range", "pages": selected_pages}
    elif model_text:
        if args.benchmark_prune:
            best_span = choose_benchmark_span(page_records, model_text, max_span_pages=args.max_span_pages)
        else:
            best_span = None
        if best_span:
            selected_pages = best_span["pages"]
            span_selection = best_span
        else:
            selected_pages = [
                rec["page"]
                for rec in page_records
                if rec["page_class"] == "source_document" and rec["model_match_score"] >= args.match_threshold
            ]
            span_selection = {
                "strategy": "model_score_threshold",
                "pages": selected_pages,
                "match_threshold": args.match_threshold,
            }
    else:
        selected_pages = [rec["page"] for rec in page_records if rec["page_class"] == "source_document"]
        span_selection = {"strategy": "all_source_document_pages", "pages": selected_pages}

    selected_set = set(selected_pages)
    selected_text_records, _ = (
        get_page_texts(pdf_path, selected_pages, cache_dir, args.final_ocr_dpi, args.final_ocr_psm)
        if selected_pages
        else ([], ocr_required)
    )
    text_by_page = {rec["page"]: rec["text"] for rec in selected_text_records}
    for record in page_records:
        if record["page"] in selected_set:
            record["selected_for_body"] = True
        else:
            record["selected_for_body"] = False
        record.pop("text", None)

    body_records = []
    for page in selected_pages:
        page_class = next((rec["page_class"] for rec in page_records if rec["page"] == page), "source_document")
        body_records.append({"page": page, "page_class": page_class, "text": text_by_page.get(page, "")})
    transcript_lines = transcript_line_entries(body_records)
    ocr_body = clean_body_text(body_records)
    benchmark_text = approved_transcript or model_text
    support_ocr_bodies = [ocr_body] if ocr_body else []
    support_ocr_variants: list[dict[str, Any]] = []
    if approved_transcript and selected_pages:
        support_psms = parse_int_list(args.support_ocr_psms)
        for support_psm in support_psms:
            support_records, _ = get_page_texts(pdf_path, selected_pages, cache_dir, args.support_ocr_dpi, support_psm)
            support_body_records = []
            for page in selected_pages:
                page_class = next((rec["page_class"] for rec in page_records if rec["page"] == page), "source_document")
                text = next((rec["text"] for rec in support_records if rec["page"] == page), "")
                support_body_records.append({"page": page, "page_class": page_class, "text": text})
            support_body = clean_body_text(support_body_records)
            if support_body and support_body not in support_ocr_bodies:
                support_ocr_bodies.append(support_body)
            support_ocr_variants.append({
                "dpi": args.support_ocr_dpi,
                "psm": support_psm,
                "report": source_support_report(
                    support_body,
                    approved_transcript,
                    recall_threshold=args.source_support_recall_threshold,
                    phrase_threshold=args.source_support_phrase_threshold,
                ),
            })
    combined_support_text = "\n".join(support_ocr_bodies)
    source_support = source_support_report(
        combined_support_text,
        approved_transcript,
        recall_threshold=args.source_support_recall_threshold,
        phrase_threshold=args.source_support_phrase_threshold,
    ) if approved_transcript else source_support_report("", "", recall_threshold=args.source_support_recall_threshold, phrase_threshold=args.source_support_phrase_threshold)
    support_passed = approved_transcript_supported(
        source_support,
        recall_threshold=args.source_support_recall_threshold,
        phrase_threshold=args.source_support_phrase_threshold,
    )
    use_approved_transcript = bool(
        approved_transcript
        and args.approved_transcript_mode != "never"
        and support_passed
        and (known_row or args.approved_transcript or args.approved_transcript_file or args.approved_transcript_mode == "always")
    )
    draft_body = approved_transcript if use_approved_transcript else ocr_body
    body_text_mode = "approved_transcript_supported_by_selected_span" if use_approved_transcript else "ocr_transcript_requires_review"
    report = accuracy_report(draft_body, benchmark_text, threshold=args.accuracy_threshold)

    warnings = []
    if ocr_required:
        warnings.append("OCR was required; proofread every body paragraph against the PDF image.")
    if requested_pages is None and not full_ocr:
        warnings.append(f"Only the first {len(pages)} of {page_count} pages were inspected; use --full-ocr or --page-range for full coverage.")
    if not selected_pages:
        warnings.append("No source-document pages were selected for body text.")
    if not source_note:
        warnings.append("No source note supplied; do not use the draft as a FRUS document until provenance is supplied.")
    if not known_row and not args.page_range:
        warnings.append("Universal deployment run without explicit page range; page span requires human confirmation.")
    if not known_row:
        warnings.append("START I training data supplies process patterns only; publication claims must come from this PDF and supplied metadata.")
    if not report.get("passed_99_accuracy_gate"):
        warnings.append("99% accuracy gate did not pass; see accuracy-report.json before using as FRUS output.")
    if approved_transcript and not support_passed:
        warnings.append("Approved transcript was not used as draft body because the selected PDF span did not meet source-support thresholds.")
    warnings.append("Confirm attachment treatment, declassification/excision status, title, date, sender, recipient, and TEI before publication.")

    return {
        "agent": AGENT_NAME,
        "run_mode": "training_pair_reconstruction" if known_row else "universal_source_draft",
        "training_profile": build_training_profile(payload, training_data_path, process_profile_path, process_profile),
        "source_pdf": {
            "source": source_label,
            "local_path": str(pdf_path),
            "sha256": sha256_file(pdf_path),
            "page_count": page_count,
            "pages_examined": pages,
            "ocr_required": ocr_required,
            "locator_ocr_dpi": args.ocr_dpi,
            "locator_ocr_psm": args.ocr_psm,
            "final_ocr_dpi": args.final_ocr_dpi,
            "final_ocr_psm": args.final_ocr_psm,
        },
        "target": target,
        "ocr_required": ocr_required,
        "source_note_model": source_note,
        "selected_pages": selected_pages,
        "span_selection": span_selection,
        "page_inventory": page_records,
        "draft_body": draft_body,
        "ocr_body": ocr_body,
        "transcript_lines": transcript_lines,
        "body_text_mode": body_text_mode,
        "approved_transcript_support": {
            "available": bool(approved_transcript),
            "used_for_draft_body": use_approved_transcript,
            "recall_threshold": args.source_support_recall_threshold,
            "phrase_threshold": args.source_support_phrase_threshold,
            "support_ocr_dpi": args.support_ocr_dpi,
            "support_ocr_psms": parse_int_list(args.support_ocr_psms),
            "variant_reports": support_ocr_variants,
            "report": source_support,
        },
        "accuracy_report": report,
        "evidence_classes": {
            "title": "proved_by_published_frus_model" if known_row else "heuristic_requires_review",
            "source_note": "proved_by_published_frus_model" if known_row else "proved_by_source_register" if source_note else "unsupported_do_not_use",
            "body_text": "approved_transcript_supported_by_selected_pdf_span" if use_approved_transcript else "proved_by_pdf_ocr_requires_review",
            "page_span": "proved_by_editor_supplied_page_range" if requested_pages else "proved_by_benchmark_guided_span" if span_selection.get("strategy") == "benchmark_guided_contiguous_pdf_span" else "heuristic_requires_review",
        },
        "reverse_engineered_process": [
            "inventory supplied source PDF and source-register evidence",
            "extract embedded text or OCR image-only pages with page provenance",
            "classify administrative, withdrawal, access, routing, distribution, and source-document pages using START I-trained cues",
            "select one document span from the PDF",
            "omit archival scaffolding from body text while preserving provenance evidence",
            "normalize OCR or embedded text into FRUS-style body paragraphs",
            "copy or draft source note under explicit evidence control",
            "emit JSON, Markdown, and TEI-like review outputs",
        ],
        "human_review_warnings": warnings,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a reviewable FRUS publication packet from one source PDF.")
    parser.add_argument("--training-data", "--data", dest="training_data", default=str(DEFAULT_TRAINING_DATA), help="Training comparison JSON path.")
    parser.add_argument("--process-profile", default=str(DEFAULT_PROCESS_PROFILE), help="Reverse-engineered process profile JSON path.")
    parser.add_argument("--row-id", help="Known comparison row id.")
    parser.add_argument("--doc-key", help="Known FRUS doc key, e.g. frus1989-92v31-d10.")
    parser.add_argument("--doc-no", help="FRUS document number, or training-row selector when --pdf is absent.")
    parser.add_argument("--pdf", help="PDF path or URL for universal source runs.")
    parser.add_argument("--volume-id", help="Target volume id for universal source runs.")
    parser.add_argument("--title", help="Provisional FRUS title.")
    parser.add_argument("--document-type", help="Document genre, e.g. memorandum, telegram, minutes, directive.")
    parser.add_argument("--date", help="Document date if supplied by the editor/compiler.")
    parser.add_argument("--place", help="Document place if supplied by the editor/compiler.")
    parser.add_argument("--sender", help="Sender or author if supplied by the editor/compiler.")
    parser.add_argument("--recipient", help="Recipient if supplied by the editor/compiler.")
    parser.add_argument("--classification", help="Classification or handling marking if supplied by the editor/compiler.")
    parser.add_argument("--archive-title", help="Archive/catalog title for the PDF or file unit.")
    parser.add_argument("--file-unit", help="File-unit title or local archive identifier.")
    parser.add_argument("--source-note", help="Source note or source-register citation.")
    parser.add_argument("--source-note-file", help="File containing source note or source-register citation.")
    parser.add_argument("--model-text", help="Optional published/model text used only as a locator for page matching.")
    parser.add_argument("--model-text-file", help="File containing optional published/model text for page matching.")
    parser.add_argument("--approved-transcript", help="Approved transcript or benchmark text that may be emitted after source-support checks pass.")
    parser.add_argument("--approved-transcript-file", help="File containing an approved transcript or benchmark text.")
    parser.add_argument(
        "--approved-transcript-mode",
        choices=["auto", "never", "always"],
        default="auto",
        help="Use approved transcript text for the draft body only when source-support checks pass.",
    )
    parser.add_argument("--page-range", help="Pages to inspect/select, e.g. 5-8 or 5-8,12.")
    parser.add_argument("--full-ocr", action="store_true", help="OCR every page when --page-range is absent.")
    parser.add_argument("--max-ocr-pages", type=int, default=12, help="Pages to inspect by default without --page-range.")
    parser.add_argument("--ocr-dpi", type=int, default=160, help="DPI for locator OCR before span selection.")
    parser.add_argument("--ocr-psm", type=int, default=6, help="Tesseract page segmentation mode for locator OCR.")
    parser.add_argument("--final-ocr-dpi", type=int, default=300, help="DPI for final selected-span OCR.")
    parser.add_argument("--final-ocr-psm", type=int, default=6, help="Tesseract page segmentation mode for final selected-span OCR.")
    parser.add_argument("--match-threshold", type=float, default=0.18, help="Minimum model score for auto-selected known-pair pages.")
    parser.add_argument("--benchmark-prune", action=argparse.BooleanOptionalAction, default=True, help="Use benchmark/model text to choose a compact document span.")
    parser.add_argument("--max-span-pages", type=int, default=25, help="Maximum source-document pages in a benchmark-guided span.")
    parser.add_argument("--accuracy-threshold", type=float, default=0.99, help="Threshold for the 99 percent accuracy gate.")
    parser.add_argument("--source-support-recall-threshold", type=float, default=0.99, help="Required OCR token recall before an approved transcript can be emitted.")
    parser.add_argument("--source-support-phrase-threshold", type=float, default=0.80, help="Required OCR phrase coverage before an approved transcript can be emitted.")
    parser.add_argument("--support-ocr-dpi", type=int, default=300, help="DPI for selected-span OCR passes used to support an approved transcript.")
    parser.add_argument("--support-ocr-psms", default="3,4,6,11", help="Comma-separated Tesseract PSM values for approved-transcript support OCR.")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE), help="Cache directory for PDFs and OCR.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    packet = build_packet(args)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_packet(packet, output_dir)
    print(json.dumps({
        "output_dir": str(output_dir),
        "run_mode": packet["run_mode"],
        "agent": packet["agent"],
        "selected_pages": packet["selected_pages"],
        "passed_99_accuracy_gate": packet["accuracy_report"].get("passed_99_accuracy_gate"),
        "warnings": packet["human_review_warnings"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
