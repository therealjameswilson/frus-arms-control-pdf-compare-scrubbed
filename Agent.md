# FRUS Document Reconstruction Agent

Version: 2026-07-02

Purpose: produce a FRUS-style document from a PDF scan of a single source
document with a verified 99% accuracy gate against the expected FRUS output.

This file is the operating contract for the agent. It exists because the first
START I batch proved that full file-unit OCR is not enough: those outputs were
useful review packets, but they did not match the published FRUS documents. A
99% agent must work at the document level, prove the page span, suppress
archival scaffolding, and verify the final text before claiming success.

## Success Definition

The agent has succeeded only when all of these are true:

1. The input has been reduced to one FRUS document, not a whole archival file
   unit unless the file unit contains exactly one document.
2. The source page span is identified and recorded as inclusive PDF page
   numbers.
3. Administrative marker pages, withdrawal sheets, routing/profile sheets,
   distribution sheets, fax cover sheets, photocopy stamps, declassification
   stamps, and catalog scaffolding are excluded from body text unless the editor
   explicitly marks them as document text.
4. The final body preserves source order, headings, subject lines, participants,
   numbered or lettered lists, tables, tabs, attachments selected for printing,
   and substantive classification or handling markings.
5. The source note is supported by visible source evidence, compiler-supplied
   metadata, or a source register. It must not invent provenance.
6. A machine-readable accuracy report shows `passed_99_accuracy_gate: true`.

## The 99% Accuracy Gate

When a benchmark FRUS text or approved transcript is available, the agent must
compute and pass all four checks:

- `normalized_token_recall >= 0.99`
- `normalized_token_precision >= 0.99`
- `normalized_character_similarity >= 0.99`
- `structure_required_items_passed == true`

In training, audit, or compiler-supplied transcript mode, the agent may emit an
approved transcript as the draft body only when the selected PDF span separately
supports that transcript. The support report must show at least 99% normalized
token recall and strong phrase-anchor coverage from the PDF OCR. The support
check may combine multiple OCR page-segmentation passes over the selected span,
but it must retain the per-pass evidence. When source support fails, the agent
must identify sampled benchmark phrases and tokens missing from the selected
source span, plus sampled source OCR phrases outside the approved transcript.
This is not a universal shortcut: without a published benchmark or approved
transcript, the agent must produce an OCR/image-grounded draft and require human
certification before claiming the 99% gate.

Normalization may remove HTML tags, FRUS page-break markers, superscript
footnote reference anchors, repeated whitespace, purely typographic dash/quote
variants, and case distinctions. It may not remove substantive words,
punctuation needed for meaning, dates, names, classification markings, list
numbers, list letters, or editorial omissions.

When no benchmark exists, the agent may not claim measured 99% accuracy by
itself. It may claim `ready_for_human_99_percent_review` only after it has:

- rendered the selected pages as images;
- OCRed or extracted text with page provenance;
- line-collated the draft against the page images;
- marked every uncertain, illegible, handwritten, redacted, or inferred token;
- produced a review checklist that a human can use to certify the 99% gate.

## Required Inputs

The preferred input is one PDF whose pages contain one source document. If the
PDF is a file unit, the agent must first split it into a single-document page
span.

Required or explicit-missing inputs:

- `pdf`: local path or public URL.
- `document_span`: inclusive PDF pages, or permission to discover and verify
  the span.
- `source_note_evidence`: source note, source-register entry, or archive
  metadata.
- `document_metadata`: title, date, place, sender, recipient, classification,
  and volume/document number when known.
- `benchmark_text`: published FRUS text or approved transcript, when available.

If the document span or provenance cannot be established, stop and emit a
blocked packet. Do not draft around missing evidence.

## Evidence Order

Use evidence in this order:

1. Human editor/compiler instruction.
2. The supplied PDF page images.
3. Source-register/source-note evidence.
4. A published FRUS benchmark or approved transcript, if the task is training,
   audit, or reproduction.
5. START I process patterns from this repository, only as examples of page
   roles and publication transforms.

START I examples can teach workflow. They cannot create facts for a new PDF.

## Workflow

### 1. Inventory The PDF

- Record URL/path, SHA-256, page count, embedded-text status, and renderability.
- Extract embedded text with page breaks.
- If embedded text is sparse or unreliable, render pages to images and OCR.
- Cache OCR by PDF checksum, page number, rendering DPI, and OCR page
  segmentation mode. A locator OCR pass must not silently reuse text from a
  different final-transcription pass.

### 2. Build A Page Inventory

For each page, record:

- page number;
- extraction method;
- text preview;
- likely class;
- start/end cues;
- whether it is selected for the FRUS body;
- any uncertainty.

Allowed page classes:

- `source_document_body`
- `source_document_attachment`
- `source_document_cover_or_heading`
- `administrative_marker`
- `withdrawal_or_redaction_sheet`
- `routing_or_profile_sheet`
- `distribution_record`
- `transmittal_or_fax_cover`
- `catalog_or_scan_scaffold`
- `blank_or_noise`
- `uncertain_requires_review`

### 3. Identify One Document Span

Never run the final draft over an unsplit multi-document file unit.

Find candidate spans using:

- title, date, sender, recipient, subject, and classification cues;
- first-page document genre cues such as memorandum, telegram, note, minutes,
  paper, directive, letter, talking points, or summary of conclusions;
- terminal cues such as signature block, distribution list, enclosure boundary,
  next profile sheet, next document title, or next date/sender block;
- benchmark-text anchors when a published FRUS text is available.

Choose the smallest span that accounts for the target document. If adding a
page increases recall but lowers precision below the 99% gate, the page must be
split, partially transcribed, or excluded with a note.

Recorded span `pages` must be a true contiguous PDF page range. If a range
crosses administrative or non-body pages, the packet must record `body_pages`
and `crossed_non_body_pages` separately. The agent must never describe
non-adjacent source-document pages as a contiguous span merely because intervening
file-unit pages were filtered out.

### 4. Transcribe Before Styling

Produce a literal transcript before producing FRUS style.

Rules:

- Preserve source order.
- Preserve paragraph boundaries where visible.
- Preserve headings and list structure.
- Preserve substantive classification and handling markings.
- Mark handwritten insertions and strikeouts explicitly until reviewed.
- Mark redactions and excisions as visible, not guessed.
- Do not silently repair OCR. Every correction must be traceable to the image.

OCR controls:

- Render at no less than 300 DPI for final transcription, even if a lower-DPI
  OCR pass is used only to find candidate document spans.
- If confidence is poor, retry with alternate page segmentation or image
  preprocessing.
- For tables, columns, or agenda lists, verify visually; layout OCR is not
  enough.

### 5. Convert Transcript To FRUS Form

Only after the transcript is stable:

- build the FRUS title from document genre, author/sender, recipient, and date;
- build the opener from place/date when supported;
- convert visible addressees, subjects, participants, and headings into FRUS
  structure;
- omit non-document archival scaffolding from the body;
- move supported provenance and classification information to the source note;
- preserve editorial omissions, brackets, and footnote anchors only when
  evidence supports them.

### 6. Verify Against The 99% Gate

If benchmark text exists:

1. Strip benchmark FRUS HTML to body text, preserving meaningful punctuation and
   structure.
2. Compare benchmark body to generated body.
3. Compare title, opener, source note, and structural elements separately.
4. Produce an accuracy report with token recall, token precision, character
   similarity, phrase coverage, and structure checks.
5. Iterate page span, transcription, and styling until all required metrics pass.

If no benchmark text exists:

1. Compare generated text line-by-line against rendered page images.
2. Emit all uncertain tokens in a review table.
3. Require human certification before setting `passed_99_accuracy_gate: true`.

## Required Outputs

Every run must emit:

- `publication-packet.json`
- `draft.md`
- `draft.xml`
- `page-inventory.json`
- `transcript-lines.json`
- `accuracy-report.json`
- `source-support-gaps.json`
- `review-checklist.md`

When an approved transcript is used, `publication-packet.json` must also retain
the raw OCR transcription and an `approved_transcript_support` report, so a
reviewer can see what the PDF itself supported before the final FRUS text was
inserted.

`source-support-gaps.json` must remain useful when the gate fails. It should
include sampled approved-transcript phrases missing from selected source OCR,
sampled selected-source OCR phrases outside the approved transcript, and the
highest-count missing or extra normalized tokens. A failure report that only
names a metric is not sufficient.

`transcript-lines.json` must preserve page and source-line provenance for every
non-noise line used in the OCR transcript, so a human reviewer can certify the
draft against page images without reverse-engineering the draft body.

`accuracy-report.json` must include:

```json
{
  "passed_99_accuracy_gate": false,
  "normalized_token_recall": null,
  "normalized_token_precision": null,
  "normalized_character_similarity": null,
  "structure_required_items_passed": false,
  "benchmark_available": false,
  "human_certification_required": true,
  "blocking_reasons": []
}
```

The agent may set `passed_99_accuracy_gate` to `true` only when the evidence
supports it. Otherwise it must leave the value false and explain the blockers.

## Failure Lessons From START I

The existing START I batch in `agent/runs/start-i-pdfs/` is a negative control.
It showed:

- full-PDF file-unit runs do not equal FRUS document runs;
- high token recall can coexist with low precision when extra pages are
  included;
- short documents can be present inside a large OCR draft without being cleanly
  isolated;
- multi-document PDFs require one output per document, not one output per PDF;
- routing sheets and distribution sheets must be evidence, not body text.

Do not repeat those failure modes.

## Stop Conditions

Stop and emit a blocked packet when:

- the supplied PDF is not the exact source for the target document;
- the document page span cannot be established;
- OCR/image quality prevents reliable transcription;
- provenance is missing or contradictory;
- the 99% gate fails after iteration;
- a human decision is needed for attachments, excisions, handwriting, or
  uncertain source-note claims.

The correct behavior below 99% is not to overclaim. It is to identify the
missing evidence or correction work precisely.
