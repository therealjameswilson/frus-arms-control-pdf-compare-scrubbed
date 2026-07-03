#!/usr/bin/env python3
"""Run the 99% FRUS agent gate across the START I training documents."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT = Path(__file__).with_name("frus_publication_agent.py")
VERIFIER = Path(__file__).with_name("verify_frus_accuracy.py")
DEFAULT_DATA = REPO_ROOT / "assets" / "data" / "frus-pdf-compare.json"
DEFAULT_OUTPUT = REPO_ROOT / "agent" / "runs" / "start-i-certified"
DEFAULT_CACHE = Path.home() / ".cache" / "frus-publication-agent"


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-").lower()


def run_command(args: list[str], *, cwd: Path, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def build_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# START I 99% Certification Batch",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Documents completed: {summary['document_count']}",
        f"- Documents requested: {summary['requested_document_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Failed: {summary['failed_count']}",
        f"- Source incomplete/blocked: {summary['source_incomplete_count']}",
        "",
        "| Doc | Status | Source status | Pages | Body mode | Support recall | Support phrase | Verifier | Output |",
        "|---:|---|---|---|---|---:|---:|---|---|",
    ]
    for result in summary["results"]:
        accuracy = result.get("accuracy_report") or {}
        support = ((result.get("approved_transcript_support") or {}).get("report") or {})
        completeness = result.get("source_completeness") or {}
        pages = ", ".join(str(page) for page in result.get("selected_pages") or [])
        status = "pass" if accuracy.get("passed_99_accuracy_gate") else "fail"
        verifier = "pass" if result.get("verifier_passed") else "fail"
        lines.append(
            "| {doc_no} | {status} | `{source_status}` | {pages} | `{mode}` | {recall} | {phrase} | {verifier} | `{output}` |".format(
                doc_no=result.get("doc_no"),
                status=status,
                source_status=completeness.get("status") or "",
                pages=pages or "none",
                mode=result.get("body_text_mode") or "",
                recall=support.get("normalized_token_recall"),
                phrase=support.get("phrase_coverage"),
                verifier=verifier,
                output=result.get("output_dir"),
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def build_summary(data_path: Path, rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [
        result
        for result in results
        if result.get("accuracy_report", {}).get("passed_99_accuracy_gate") and result.get("verifier_passed")
    ]
    source_incomplete = [
        result
        for result in results
        if str((result.get("source_completeness") or {}).get("status") or "").startswith("source_incomplete")
    ]
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "data": str(data_path.relative_to(REPO_ROOT)),
        "requested_document_count": len(rows),
        "document_count": len(results),
        "passed_count": len(passed),
        "failed_count": len(results) - len(passed),
        "source_incomplete_count": len(source_incomplete),
        "results": results,
    }


def write_summary(output_root: Path, data_path: Path, rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = build_summary(data_path, rows, results)
    write_json(output_root / "batch-summary.json", summary)
    (output_root / "batch-summary.md").write_text(build_markdown(summary), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run START I documents through the FRUS 99% certification agent.")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="Comparison JSON path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Batch output directory.")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE), help="Shared PDF/OCR cache directory.")
    parser.add_argument("--limit", type=int, help="Limit number of documents for smoke tests.")
    parser.add_argument("--doc-no", action="append", help="Run only this FRUS document number; may be repeated.")
    parser.add_argument("--support-ocr-psms", default="3,4,6,11", help="Support OCR PSM list passed to the agent.")
    parser.add_argument("--resume", action="store_true", help="Reuse an existing publication packet when present.")
    parser.add_argument("--agent-timeout-seconds", type=int, default=0, help="Per-document agent timeout; 0 disables timeout.")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-document progress messages.")
    args = parser.parse_args(argv)

    data_path = Path(args.data).expanduser().resolve()
    output_root = Path(args.output_dir).expanduser().resolve()
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    payload = load_json(data_path)
    rows = payload.get("comparisons", [])
    if args.doc_no:
        wanted = set(str(item) for item in args.doc_no)
        rows = [row for row in rows if str(row.get("doc_no")) in wanted]
    if args.limit:
        rows = rows[: args.limit]

    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        doc_no = str(row["doc_no"])
        doc_key = row["doc_key"]
        doc_dir = output_root / f"{index:02d}-d{doc_no}-{slug(doc_key)}"
        doc_dir.mkdir(parents=True, exist_ok=True)
        packet_path = doc_dir / "publication-packet.json"
        if not args.quiet:
            print(f"[{index}/{len(rows)}] doc {doc_no} {doc_key}", flush=True)
        if not (args.resume and packet_path.exists()):
            cmd = [
                sys.executable,
                str(AGENT),
                "--doc-key",
                doc_key,
                "--full-ocr",
                "--cache-dir",
                str(cache_dir),
                "--support-ocr-psms",
                args.support_ocr_psms,
                "--output-dir",
                str(doc_dir),
            ]
            try:
                proc = run_command(
                    cmd,
                    cwd=REPO_ROOT,
                    timeout=args.agent_timeout_seconds or None,
                )
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="ignore")
                stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="ignore")
                (doc_dir / "agent.stdout.txt").write_text(stdout, encoding="utf-8")
                (doc_dir / "agent.stderr.txt").write_text(stderr, encoding="utf-8")
                results.append({
                    "doc_no": doc_no,
                    "doc_key": doc_key,
                    "output_dir": display_path(doc_dir),
                    "agent_returncode": None,
                    "timed_out": True,
                    "timeout_seconds": args.agent_timeout_seconds,
                    "error": f"agent timed out after {args.agent_timeout_seconds} seconds",
                })
                write_summary(output_root, data_path, rows, results)
                if not args.quiet:
                    print(f"  timed out after {args.agent_timeout_seconds}s", flush=True)
                continue
            (doc_dir / "agent.stdout.txt").write_text(proc.stdout, encoding="utf-8")
            (doc_dir / "agent.stderr.txt").write_text(proc.stderr, encoding="utf-8")
            if proc.returncode != 0:
                results.append({
                    "doc_no": doc_no,
                    "doc_key": doc_key,
                    "output_dir": display_path(doc_dir),
                    "agent_returncode": proc.returncode,
                    "error": proc.stderr.strip() or proc.stdout.strip(),
                })
                write_summary(output_root, data_path, rows, results)
                if not args.quiet:
                    print(f"  agent failed with return code {proc.returncode}", flush=True)
                continue

        packet = load_json(packet_path)
        verifier_proc = run_command(
            [
                sys.executable,
                str(VERIFIER),
                "--candidate",
                str(packet_path),
                "--doc-key",
                doc_key,
            ],
            cwd=REPO_ROOT,
        )
        verifier_report = json.loads(verifier_proc.stdout) if verifier_proc.stdout.strip().startswith("{") else {}
        write_json(doc_dir / "verifier-report.json", verifier_report)
        results.append({
            "doc_no": doc_no,
            "doc_key": doc_key,
            "title": packet.get("target", {}).get("title"),
            "output_dir": display_path(doc_dir),
            "selected_pages": packet.get("selected_pages", []),
            "body_text_mode": packet.get("body_text_mode"),
            "source_completeness": packet.get("source_completeness", {}),
            "accuracy_report": packet.get("accuracy_report", {}),
            "approved_transcript_support": packet.get("approved_transcript_support", {}),
            "verifier_passed": verifier_proc.returncode == 0,
            "verifier_report": verifier_report,
        })
        write_summary(output_root, data_path, rows, results)
        if not args.quiet:
            status = "pass" if results[-1].get("accuracy_report", {}).get("passed_99_accuracy_gate") and results[-1].get("verifier_passed") else "fail"
            source_status = (results[-1].get("source_completeness") or {}).get("status")
            print(f"  {status}; source={source_status}; pages={results[-1].get('selected_pages')}", flush=True)

    summary = write_summary(output_root, data_path, rows, results)
    print(json.dumps({
        "output_dir": str(output_root),
        "document_count": summary["document_count"],
        "passed_count": summary["passed_count"],
        "failed_count": summary["failed_count"],
    }, indent=2))
    return 0 if summary["failed_count"] == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted; partial batch summary is available for completed documents.", file=sys.stderr)
        raise SystemExit(130)
