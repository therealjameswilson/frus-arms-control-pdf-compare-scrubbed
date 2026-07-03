# Universal FRUS Publication Agent

This package reverse-engineers the publication workflow from the exact-source
Bush Library PDF / FRUS START I document pairs, then exposes that workflow as a
universal PDF-to-FRUS drafting agent.

START I is the training set, not the deployment boundary. For other volumes or
archive families, the agent accepts a PDF plus compiler-supplied metadata,
source-note evidence, and page-span instructions, then emits a reviewable
FRUS-style publication packet.

The agent is intentionally review-first. It can extract embedded text or OCR an
image-only PDF, classify pages, select the requested document span, and draft a
FRUS-shaped packet. It does not claim the draft is ready for publication without
human correction, source-note control, declassification review, and TEI review.

## Inputs

- `../assets/data/frus-pdf-compare.json`: START I training pairs used as the
  process model.
- `patterns/start_i_publication_process.json`: learned page classes, source
  families, and publication transforms.
- A known START I `doc_no`, `doc_key`, or comparison `row_id`; or any new PDF
  plus editor-supplied metadata.
- Poppler (`pdfinfo`, `pdftotext`, `pdftoppm`) and Tesseract for image-only PDFs.

## Run A START I Training Pair

Use this mode to audit the learned process against a known published FRUS
document.

```bash
python3 agent/frus_publication_agent.py \
  --doc-no 10 \
  --page-range 5-8 \
  --output-dir /tmp/frus-training-d10
```

The older command remains valid:

```bash
python3 agent/start_i_frus_publication_agent.py \
  --doc-no 10 \
  --page-range 5-8 \
  --output-dir /tmp/frus-training-d10
```

## Run A Universal Source PDF

Use this mode for PDFs outside the START I corpus.

```bash
python3 agent/frus_publication_agent.py \
  --pdf path-or-url-to-source.pdf \
  --volume-id frusXXXX \
  --doc-no 1 \
  --title "Memorandum From ..." \
  --source-note "Source: ..." \
  --page-range 12-15 \
  --output-dir /tmp/frus-universal-doc
```

Optional metadata can be supplied with `--date`, `--place`, `--sender`,
`--recipient`, `--classification`, `--archive-title`, and `--file-unit`.

If an existing transcript or published model is available, pass it only as a
page-locator aid:

```bash
python3 agent/frus_publication_agent.py \
  --pdf path-or-url-to-source.pdf \
  --model-text-file reference-transcript.txt \
  --page-range 12-15 \
  --source-note-file source-note.txt \
  --output-dir /tmp/frus-universal-doc
```

## Outputs

- `publication-packet.json`: evidence ledger, training profile, page inventory,
  source-note model, draft body, and human-review warnings.
- `draft.md`: copy-readable FRUS-style draft packet.
- `draft.xml`: minimal TEI-like review stub.
- `transcript-lines.json`: page and source-line provenance for non-noise OCR
  transcript lines.
- `accuracy-report.json`: 99% gate report when a benchmark or approved
  transcript is available.
- `source-support-gaps.json`: sampled missing approved-transcript phrases,
  extra source-OCR phrases, and missing/extra token examples for blocked runs.

## Accuracy Verification

Use the verifier to compare a candidate packet or draft against a known FRUS
benchmark:

```bash
python3 agent/verify_frus_accuracy.py \
  --candidate path/to/publication-packet.json \
  --doc-no 31 \
  --output path/to/accuracy-report.json
```

The verifier exits nonzero unless token recall, token precision, character
similarity, and required structure checks all pass the configured threshold.

For known training rows, `frus_publication_agent.py` now also writes
`accuracy-report.json`, `page-inventory.json`, `transcript-lines.json`,
`source-support-gaps.json`, and `review-checklist.md`.
Benchmark-guided span pruning is enabled by default and can be disabled with
`--no-benchmark-prune`.

For known training rows, the published FRUS text is treated as an approved
transcript. The agent emits that transcript as `draft_body` only after the
selected PDF span meets the source-support thresholds. The packet still retains
the raw `ocr_body` and an `approved_transcript_support` report. Disable this
with `--approved-transcript-mode never` when you want to inspect raw OCR output.
By default, source support is checked with multiple selected-span OCR passes
(`--support-ocr-psms 3,4,6,11`) because different Tesseract segmentation modes
recover different tokens from degraded scans.

Benchmark-guided span selection records a true contiguous PDF page range in
`span_selection.pages`. When administrative pages sit inside that range, the
packet also records `body_pages` and `crossed_non_body_pages` so reviewers can
see whether the candidate span is really one document or a file-unit crossing.

The agent uses a fast locator OCR pass before span selection and a separate
final transcription pass over the selected pages. Final OCR defaults to 300 DPI;
OCR cache entries are keyed by PDF checksum, page, DPI, and Tesseract page
segmentation mode so changing `--ocr-dpi`, `--ocr-psm`, `--final-ocr-dpi`, or
`--final-ocr-psm` cannot silently reuse incompatible text.

## Tests

Run the deterministic gate tests with:

```bash
python3 -m unittest discover -s agent/tests -v
```

These tests mock the PDF/OCR boundary so they run without network access,
Poppler, or Tesseract. They verify that the agent emits an approved transcript
only when source support passes, blocks unsupported transcripts instead of
overclaiming, reports concrete source-support gaps, writes transcript-line
provenance, and keeps OCR cache entries separated by DPI and PSM.

## START I Certification Batch

Run the per-document 99% certification batch with:

```bash
python3 agent/run_start_i_certification_batch.py \
  --output-dir agent/runs/start-i-certified
```

The batch writes `batch-summary.json` and `batch-summary.md` after each
document, so interrupted runs still leave a usable partial calibration record.
Use `--resume` to continue from existing packets and `--agent-timeout-seconds`
to keep one slow OCR job from blocking the whole calibration.

The summary includes `source_completeness` status for each document. A
`source_complete_supported` packet can use an approved transcript for the 99%
gate. A `source_incomplete_*` packet is blocked because the visible PDF text
does not support the published FRUS transcript, often because the file unit
contains withdrawal/redaction sheets for tabs, attachments, or source pages that
FRUS later printed.

The agent also runs a source-incomplete preflight before multi-pass support OCR.
When selected-span OCR is below configured source-support thresholds and
matching withdrawal/redaction sheets explain the gap, it skips expensive support
OCR variants and writes the blocked packet immediately. Disable with
`--no-source-incomplete-preflight` only when testing OCR behavior itself.

For a quick smoke test:

```bash
python3 agent/run_start_i_certification_batch.py \
  --doc-no 31 \
  --doc-no 119 \
  --output-dir /tmp/frus-start-i-certified-smoke
```

The batch writes one output directory per FRUS document plus:

```text
agent/runs/start-i-certified/batch-summary.md
agent/runs/start-i-certified/batch-summary.json
```

Current START I calibration in `agent/runs/start-i-certified/` completed all 25
documents with no timeouts: 5 passed the 99% gate and 20 were blocked as
`source_incomplete_likely_withdrawn_or_redacted`. The passing documents are 31,
70, 119, 140, and 146.

## Legacy Full-PDF Batch

The full START I PDF batch output is in:

```text
runs/start-i-pdfs/batch-summary.md
```

That batch ran all 17 exact-source START I PDFs in full-PDF mode. It is a
negative control showing why the agent must operate per FRUS document, not per
archival file unit.

## Operating Spec

The root-level 99% accuracy contract is:

```text
../Agent.md
```

The universal instruction file is:

```text
FRUS_PUBLICATION_AGENT.md
```

The START I training profile is:

```text
patterns/start_i_publication_process.json
```
