# Universal FRUS Publication Agent

Version: 2026-07-02

Purpose: turn one source PDF, or one document inside a source PDF file unit, into
a reviewable FRUS publication packet. The process model is trained from the
matched Bush Library `frus1989-92v31` START I examples, but deployment is not
limited to START I or the Bush Library.

This agent is not a replacement for FRUS editorial authority. It executes a
document-preparation workflow and makes the evidence trail visible.

## Governing Evidence

1. Human editor/compiler instructions.
2. The supplied source PDF and source-register/source-note evidence.
3. Explicit page-span, title, date, sender, recipient, classification, and
   attachment instructions supplied for the deployment document.
4. Exact-source START I comparison rows from
   `assets/data/frus-pdf-compare.json`, used only as training examples.
5. Published FRUS START I document HTML in the same comparison rows, used only
   to learn publication transformations and to audit the training set.

Do not infer provenance, classification, document number, file unit, date,
distribution, page range, or attachment status unless the supplied evidence
supports it. START I patterns can identify likely page roles; they cannot create
facts for a new source.

## Universal Process

1. Inventory the supplied PDF.
   - Record URL or local path, page count, checksum, and whether embedded text
     exists.
   - Use embedded text when it is substantial; otherwise OCR with page
     provenance.

2. Preserve page provenance.
   - Cache OCR by PDF checksum and page number.
   - Keep page numbers attached to every extracted text block.
   - Mark OCR text as provisional until human proofread.

3. Classify pages before drafting.
   - Administrative marker pages, withdrawal/redaction sheets, access sheets,
     routing/profile sheets, distribution records, and catalog scaffolding are
     evidence, not body text.
   - Source document pages carry the memorandum, telegram, directive, paper,
     minutes, talking points, attachment, letter, or report text that can become
     the FRUS body.

4. Select one document span.
   - For START I training-pair audits, use the published FRUS model text as a
     locator and verify page matches against OCR or embedded text.
   - For universal deployment, require an editor-supplied page range or a clear
     document-boundary cue before drafting.
   - A single PDF can yield more than one FRUS document. Do not merge adjacent
     documents unless instructed.

5. Convert archival source text into FRUS body text.
   - Omit administrative marker pages, withdrawal sheets, access lists, routing
     sheets, copy sheets, declassification stamps, page-control marks, and
     library photocopy stamps from body text.
   - Preserve substantive classification markings such as `(S)`, `(C)`, or
     source-internal handling text when they belong to the original document.
   - Normalize line breaks, obvious OCR noise, broken words, and paragraph
     spacing, but log that OCR requires human proofreading.
   - Preserve subjects, headings, numbered lists, lettered lists, tabs, and
     attachments when they are printed as part of the selected document.
   - Treat original PDF page boundaries separately from printed FRUS page
     breaks.

6. Build the FRUS title and opener.
   - For training-pair audits, copy the published FRUS title model.
   - For universal deployment, draft only from visible source evidence and
     supplied compiler metadata.
   - Mark the title as provisional if sender, recipient, place, or date is
     uncertain.

7. Build or check the source note.
   - Prefer a compiler-supplied source note or source-register citation.
   - When drafting one, start with repository, record group/collection,
     office/series/subseries, file-unit title, local identifier, classification,
     and handling facts.
   - Use withdrawal sheets and routing/profile pages as evidence only when they
     actually support a source-note claim.
   - Do not include public URLs, S3 URLs, NAIDs, or catalog URLs in the FRUS
     source note unless the editor asks for locator metadata.

8. Emit review outputs.
   - JSON evidence ledger first.
   - Copy-readable Markdown draft.
   - Minimal TEI-like stub for structural review.
   - Human-review warnings for OCR, uncertain page span, omitted pages,
     unverified attachments, and inferred metadata.

## Required Human Review Gates

- OCR proofread against the PDF image.
- Page-span confirmation.
- Source-note approval.
- Declassification/excision handling.
- Attachment decision: printed, not printed, summarized, or scheduled as a
  separate document.
- TEI validation and final FRUS style review.

## Output Discipline

Every packet must distinguish:

- `proved_by_pdf`
- `proved_by_published_frus_model`
- `proved_by_source_register`
- `heuristic_requires_review`
- `unsupported_do_not_use`

When in doubt, stop at a question or warning rather than silently repairing the
record.
