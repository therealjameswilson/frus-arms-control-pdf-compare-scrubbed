#!/usr/bin/env python3
"""Deterministic tests for the FRUS publication agent gate logic."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import frus_publication_agent as agent  # noqa: E402


APPROVED_TRANSCRIPT = "alpha beta gamma delta epsilon zeta eta theta"


def test_payload() -> dict:
    return {
        "summary": {},
        "comparisons": [
            {
                "id": "row-1",
                "doc_key": "frus-test-d1",
                "volume_id": "frus-test",
                "doc_no": "1",
                "doc_title": "1. Test Document",
                "frus_url": "https://example.test/frus/d1",
                "pdf_url": "https://example.test/source.pdf",
                "archive_title": "Test file unit",
                "source_note": "Source: Test file unit.",
                "match_basis": "unit-test",
            }
        ],
        "documents": {
            "frus-test-d1": {
                "title": "1. Test Document",
                "url": "https://example.test/frus/d1",
                "source_note": "Source: Test file unit.",
                "html": APPROVED_TRANSCRIPT,
            }
        },
    }


def args_for_packet(*extra: str):
    parser = agent.build_arg_parser()
    return parser.parse_args(
        [
            "--doc-key",
            "frus-test-d1",
            "--page-range",
            "1",
            "--support-ocr-psms",
            "3",
            "--cache-dir",
            "/tmp/frus-agent-test-cache",
            "--output-dir",
            "/tmp/frus-agent-test-output",
            *extra,
        ]
    )


class FrusPublicationAgentTests(unittest.TestCase):
    def build_packet_with_ocr(self, *, support_text: str) -> dict:
        def fake_get_page_texts(_pdf_path, pages, _cache_dir, dpi, psm):
            if dpi == 300 and psm == 3:
                text = support_text
            else:
                text = "MEMORANDUM FOR\nalpha beta gamma delta"
            return [
                {
                    "page": page,
                    "text": text,
                    "method": "ocr",
                    "ocr_dpi": dpi,
                    "ocr_psm": psm,
                }
                for page in pages
            ], True

        with (
            mock.patch.object(agent, "load_payload", return_value=test_payload()),
            mock.patch.object(agent, "load_process_profile", return_value={}),
            mock.patch.object(agent, "resolve_pdf", return_value=(Path("/tmp/fake.pdf"), "fake.pdf")),
            mock.patch.object(agent, "pdf_page_count", return_value=1),
            mock.patch.object(agent, "sha256_file", return_value="abc123"),
            mock.patch.object(agent, "get_page_texts", side_effect=fake_get_page_texts),
        ):
            return agent.build_packet(args_for_packet())

    def test_approved_transcript_is_used_only_after_source_support_passes(self) -> None:
        packet = self.build_packet_with_ocr(
            support_text=f"MEMORANDUM FOR\n{APPROVED_TRANSCRIPT}"
        )

        support = packet["approved_transcript_support"]
        self.assertEqual(packet["body_text_mode"], "approved_transcript_supported_by_selected_span")
        self.assertTrue(support["used_for_draft_body"])
        self.assertTrue(support["report"]["passed_source_support_gate"])
        self.assertTrue(packet["accuracy_report"]["passed_99_accuracy_gate"])
        self.assertEqual(packet["draft_body"], APPROVED_TRANSCRIPT)
        self.assertIn("ocr_body", packet)
        self.assertTrue(packet["transcript_lines"])
        self.assertEqual(packet["transcript_lines"][0]["page"], 1)
        self.assertEqual(packet["transcript_lines"][0]["source_line_no"], 1)
        self.assertEqual(support["report"]["gap_report"]["sampled_missing_benchmark_phrase_count"], 0)
        self.assertEqual(packet["source_completeness"]["status"], "source_complete_supported")
        self.assertTrue(packet["source_completeness"]["can_claim_99_from_pdf"])

    def test_unsupported_transcript_blocks_instead_of_overclaiming(self) -> None:
        packet = self.build_packet_with_ocr(
            support_text="MEMORANDUM FOR\nalpha beta gamma delta"
        )

        support = packet["approved_transcript_support"]
        gap_report = support["report"]["gap_report"]
        self.assertEqual(packet["body_text_mode"], "ocr_transcript_requires_review")
        self.assertFalse(support["used_for_draft_body"])
        self.assertFalse(support["report"]["passed_source_support_gate"])
        self.assertFalse(packet["accuracy_report"]["passed_99_accuracy_gate"])
        self.assertIn("source_token_recall_below_threshold", support["report"]["source_support_blocking_reasons"])
        self.assertTrue(gap_report["sampled_missing_benchmark_phrases"])
        self.assertIn("epsilon", {item["token"] for item in gap_report["top_missing_tokens"]})
        self.assertNotEqual(packet["draft_body"], APPROVED_TRANSCRIPT)
        self.assertEqual(packet["source_completeness"]["status"], "source_incomplete_or_ocr_uncertain")

    def test_gap_report_is_written_for_review(self) -> None:
        packet = self.build_packet_with_ocr(
            support_text="MEMORANDUM FOR\nalpha beta gamma delta"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            agent.output_packet(packet, output_dir)
            gaps = (output_dir / "source-support-gaps.json").read_text(encoding="utf-8")
            completeness = (output_dir / "source-completeness.json").read_text(encoding="utf-8")
            transcript = (output_dir / "transcript-lines.json").read_text(encoding="utf-8")
            cleanup = (output_dir / "ocr-editorial-cleanup.json").read_text(encoding="utf-8")
            style = (output_dir / "frus-style-transform.json").read_text(encoding="utf-8")
            participants = (output_dir / "frus-participants-transform.json").read_text(encoding="utf-8")
            human = (output_dir / "human-certification.json").read_text(encoding="utf-8")
            checklist = (output_dir / "review-checklist.md").read_text(encoding="utf-8")

        self.assertIn("sampled_missing_benchmark_phrases", gaps)
        self.assertIn("source_incomplete_or_ocr_uncertain", completeness)
        self.assertIn("source_line_no", transcript)
        self.assertIn("removed_line_count", cleanup)
        self.assertIn("applied", style)
        self.assertIn("applied", participants)
        self.assertIn("requires_correction_or_source_review", human)
        self.assertIn("Source Completeness", checklist)
        self.assertIn("Sample benchmark phrases not supported", checklist)
        self.assertIn("OCR Editorial Cleanup", checklist)
        self.assertIn("FRUS Style Transform", checklist)
        self.assertIn("FRUS Participants Transform", checklist)
        self.assertIn("Human Certification", checklist)

    def test_frus_editorial_cleanup_removes_scan_scaffolding_with_audit_trail(self) -> None:
        cleaned, report = agent.frus_editorial_cleanup(
            "NATIONAL SECURITY COUNCIL 20937\n"
            "| WASHINGTON, D.C. 20506\n"
            "Substantive sentence. (3)\n"
            "7 PER E.0. 13526\n"
            "Declassify on: OADR\n"
            "- * gaid another point. (8%\n"
            "= 4\n"
        )

        self.assertNotIn("NATIONAL SECURITY COUNCIL", cleaned)
        self.assertNotIn("Declassify on", cleaned)
        self.assertIn("Substantive sentence. (S)", cleaned)
        self.assertIn("said another point. (S)", cleaned)
        self.assertEqual(report["removed_line_count"], 5)
        self.assertEqual(report["replacement_count"], 2)

    def test_frus_opener_transform_builds_heading_from_source_header(self) -> None:
        cleaned = "\n".join(
            [
                "Summary of Conclusions for",
                "The Deputies Committee Meeting",
                "DATE: June 12, 1989",
                "LOCATION: Situation Room",
                "TIME: 11:00 AM - NOON",
                "SUBJECT: Summary of Conclusions",
                "Body starts here.",
            ]
        )

        transformed, report = agent.frus_opener_transform(
            cleaned,
            "WASHINGTON, D.C. 20506",
            {"title": "31. Summary of Conclusions for a Deputies Committee Meeting 1"},
        )

        self.assertTrue(report["applied"])
        self.assertIn("31. Summary of Conclusions for a Deputies Committee Meeting", transformed.splitlines()[0])
        self.assertIn("Washington, June 12, 1989, 11 a.m.-noon", transformed.splitlines()[0])
        self.assertNotIn("DATE:", transformed)
        self.assertIn("SUBJECT: Summary of Conclusions", transformed)

    def test_participant_column_transform_reorders_two_column_meeting_list(self) -> None:
        styled = "\n".join(
            [
                "31. Summary of Conclusions for a Deputies Committee Meeting Washington, June 12, 1989, 11 a.m.-noon",
                "SUBJECT: Summary of Conclusions",
                "PARTICIPANTS:",
                "The Vice President's Office CIA:",
                "Carnes Lord Richard. Kerr",
                "Douglas MacEachin",
                "State:",
                "Reginald Bartholomew JCS:",
                "Edward Rowny John Baldwin",
                "Richard Burt Thomas Fox",
                "Roger Harrison",
                "ACDA:",
                "Defense: George Murphy.",
                "Donald Atwood William Fite",
                "Paul Wolfowitz",
                "Stephen Hadley White House:",
                "Robert Gates",
                "Energy:",
                "John Tuck NSC:",
                "Victor Alessi Arnold Kanter",
                "Richard Davis",
                "OMB:",
                "William Diefenderfer",
                "Frank Hodsoll",
                "Summary of Conclusions",
                "There was agreement.",
            ]
        )

        transformed, report = agent.frus_participant_column_transform(styled)
        norm = agent.normalized_chars(transformed)

        self.assertTrue(report["applied"])
        self.assertIn(
            "participants the vice president office carnes lord state reginald bartholomew edward rowny richard burt roger harrison defense donald atwood paul wolfowitz stephen hadley energy john tuck victor alessi omb william diefenderfer frank hodsoll cia richard kerr douglas maceachin jcs john baldwin thomas fox acda george murphy william fite white house robert gates nsc arnold kanter richard davis summary of conclusions",
            norm,
        )
        self.assertEqual(report["group_count"], 10)

    def test_transcript_line_entries_flags_uncertain_lines(self) -> None:
        entries = agent.transcript_line_entries(
            [
                {
                    "page": 4,
                    "page_class": "source_document",
                    "text": "Clear line\n[illegible handwritten deletion]\nText ____ uncertain",
                }
            ]
        )

        flagged = [entry for entry in entries if entry["review_flags"]]
        self.assertEqual(len(flagged), 2)
        self.assertIn("editorial_uncertainty_marker", flagged[0]["review_flags"])
        self.assertIn("handwriting_or_illegible_marker", flagged[0]["review_flags"])
        self.assertIn("ocr_noise_or_uncertain_marks", flagged[1]["review_flags"])

    def test_universal_run_defaults_to_human_review_images_without_approved_transcript(self) -> None:
        def fake_get_page_texts(_pdf_path, pages, _cache_dir, _dpi, _psm):
            return [
                {
                    "page": page,
                    "text": "MEMORANDUM FOR THE PRESIDENT\nSubject: Test\nalpha beta gamma",
                    "method": "ocr",
                }
                for page in pages
            ], True

        parser = agent.build_arg_parser()
        args = parser.parse_args(
            [
                "--pdf",
                "/tmp/fake.pdf",
                "--page-range",
                "1",
                "--source-note",
                "Source: Test file.",
                "--cache-dir",
                "/tmp/frus-agent-test-cache",
                "--output-dir",
                "/tmp/frus-agent-test-output",
            ]
        )
        with (
            mock.patch.object(agent, "load_payload", return_value=test_payload()),
            mock.patch.object(agent, "load_process_profile", return_value={}),
            mock.patch.object(agent, "resolve_pdf", return_value=(Path("/tmp/fake.pdf"), "fake.pdf")),
            mock.patch.object(agent, "pdf_page_count", return_value=1),
            mock.patch.object(agent, "sha256_file", return_value="abc123"),
            mock.patch.object(agent, "get_page_texts", side_effect=fake_get_page_texts),
        ):
            packet = agent.build_packet(args)

        human = packet["human_certification"]
        self.assertEqual(packet["run_mode"], "universal_source_draft")
        self.assertFalse(packet["accuracy_report"]["benchmark_available"])
        self.assertEqual(human["status"], "pending_review_image_render")
        self.assertEqual(human["review_image_pages"], [1])
        self.assertEqual(human["review_image_dir"], "page-images")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                agent,
                "render_review_images",
                return_value=[{"page": 1, "path": "page-images/page-0001.png", "dpi": 150}],
            ):
                agent.output_packet(packet, Path(tmp))
            human_text = (Path(tmp) / "human-certification.json").read_text(encoding="utf-8")

        self.assertIn("ready_for_human_99_percent_review", human_text)

    def test_source_completeness_flags_matching_withdrawal_sheet(self) -> None:
        source_support = agent.source_support_report(
            "alpha beta gamma delta",
            "memorandum from scowcroft to president bush arms control review",
            recall_threshold=0.99,
            phrase_threshold=0.8,
        )
        completeness = agent.source_completeness_report(
            [
                {
                    "page": 2,
                    "page_class": "withdrawal_sheet",
                    "text_preview": "03a. Memo Brent Scowcroft to POTUS Re: Arms Control Review (2 pp.)",
                }
            ],
            "memorandum from scowcroft to president bush arms control review",
            source_support,
            {"title": "Memorandum From Scowcroft to President Bush"},
            "Source: Secret. Sent for action.",
        )

        self.assertEqual(completeness["status"], "source_incomplete_likely_withdrawn_or_redacted")
        self.assertFalse(completeness["can_claim_99_from_pdf"])
        self.assertEqual(completeness["matching_withdrawal_pages"][0]["page"], 2)

    def test_source_incomplete_preflight_skips_expensive_support_ocr(self) -> None:
        payload = test_payload()
        payload["documents"]["frus-test-d1"]["html"] = (
            "memorandum from scowcroft to president bush arms control review omega final"
        )
        support_calls: list[tuple[int, int, tuple[int, ...]]] = []

        def fake_get_page_texts(_pdf_path, pages, _cache_dir, dpi, psm):
            if dpi == 160:
                text_by_page = {
                    1: "MEMORANDUM FOR\nalpha beta gamma delta",
                    2: "Withdrawal/Redaction Sheet. 03a. Memo Brent Scowcroft to POTUS Re: Arms Control Review.",
                }
            elif dpi == 300 and psm in {3, 6}:
                text_by_page = {1: "MEMORANDUM FOR\nalpha beta gamma delta"}
            else:
                support_calls.append((dpi, psm, tuple(pages)))
                raise AssertionError("support OCR should be skipped by source-incomplete preflight")
            return [
                {
                    "page": page,
                    "text": text_by_page.get(page, ""),
                    "method": "ocr",
                    "ocr_dpi": dpi,
                    "ocr_psm": psm,
                }
                for page in pages
            ], True

        parser = agent.build_arg_parser()
        args = parser.parse_args(
            [
                "--doc-key",
                "frus-test-d1",
                "--full-ocr",
                "--support-ocr-psms",
                "3",
                "--cache-dir",
                "/tmp/frus-agent-test-cache",
                "--output-dir",
                "/tmp/frus-agent-test-output",
            ]
        )
        with (
            mock.patch.object(agent, "load_payload", return_value=payload),
            mock.patch.object(agent, "load_process_profile", return_value={}),
            mock.patch.object(agent, "resolve_pdf", return_value=(Path("/tmp/fake.pdf"), "fake.pdf")),
            mock.patch.object(agent, "pdf_page_count", return_value=2),
            mock.patch.object(agent, "sha256_file", return_value="abc123"),
            mock.patch.object(agent, "get_page_texts", side_effect=fake_get_page_texts),
        ):
            packet = agent.build_packet(args)

        support = packet["approved_transcript_support"]
        self.assertEqual(support_calls, [])
        self.assertTrue(support["source_incomplete_preflight_used"])
        self.assertTrue(support["skipped_support_ocr_variants"])
        self.assertEqual(support["variant_reports"], [])
        self.assertEqual(packet["source_completeness"]["status"], "source_incomplete_likely_withdrawn_or_redacted")

    def test_benchmark_span_uses_true_contiguous_pdf_pages(self) -> None:
        page_records = [
            {
                "page": 1,
                "page_class": "source_document",
                "text": "alpha beta gamma delta",
            },
            {
                "page": 2,
                "page_class": "administrative_marker",
                "text": "routing slip",
            },
            {
                "page": 3,
                "page_class": "source_document",
                "text": "epsilon zeta eta theta",
            },
        ]

        span = agent.choose_benchmark_span(page_records, APPROVED_TRANSCRIPT, max_span_pages=3)

        self.assertIsNotNone(span)
        self.assertEqual(span["strategy"], "benchmark_guided_contiguous_pdf_span")
        self.assertEqual(span["pages"], [1, 2, 3])
        self.assertEqual(span["body_pages"], [1, 3])
        self.assertEqual(span["crossed_non_body_pages"], [2])
        self.assertIsNone(span["normalized_character_similarity"])

    def test_benchmark_span_selection_avoids_full_accuracy_report(self) -> None:
        page_records = [
            {"page": 1, "page_class": "source_document", "text": "alpha beta gamma delta"},
            {"page": 2, "page_class": "source_document", "text": "epsilon zeta eta theta"},
        ]

        with mock.patch.object(agent, "accuracy_report", side_effect=AssertionError("too slow for span search")):
            span = agent.choose_benchmark_span(page_records, APPROVED_TRANSCRIPT, max_span_pages=2)

        self.assertIsNotNone(span)
        self.assertEqual(span["pages"], [1, 2])

    def test_withdrawal_sheet_classification_precedes_generic_admin(self) -> None:
        label, cues = agent.classify_page(
            "Withdrawal/Redaction Sheet (George Bush Library) "
            "Document No. Subject/Title of Document Record Group: Bush Presidential Records"
        )

        self.assertEqual(label, "withdrawal_sheet")
        self.assertIn("withdrawal/redaction sheet", cues)

    def test_substantive_restrictions_do_not_make_withdrawal_sheet(self) -> None:
        label, _ = agent.classify_page(
            "Memorandum for the Secretary of State. Restrictions on future systems "
            "should be reviewed by the Arms Control Policy Coordinating Committee."
        )

        self.assertEqual(label, "source_document")

    def test_ocr_cache_is_keyed_by_dpi_and_psm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ocr_dir = Path(tmp) / "ocr"
            cached = ocr_dir / "dpi-0300-psm-4" / "page-0002.txt"
            cached.parent.mkdir(parents=True)
            cached.write_text("cached psm 4 text", encoding="utf-8")

            with mock.patch.object(agent, "require_tool", return_value="tool"):
                text = agent.render_and_ocr_page(Path("/tmp/fake.pdf"), 2, ocr_dir, 300, 4)

            self.assertEqual(text, "cached psm 4 text")
            self.assertFalse((ocr_dir / "page-0002.txt").exists())


if __name__ == "__main__":
    unittest.main()
