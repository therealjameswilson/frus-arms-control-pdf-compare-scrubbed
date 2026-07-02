# START I FRUS Publication Agent

This package reverse-engineers the local workflow from the matched Bush Library
PDFs and published FRUS START I documents in this repository.

It is intentionally review-first. The runner can OCR an image-only Bush file-unit
PDF, classify its pages, locate the selected document, and draft a FRUS-shaped
publication packet. It does not claim the draft is ready for publication without
human correction, source-note control, declassification review, and TEI review.

## Inputs

- `../assets/data/frus-pdf-compare.json`: the 25 exact-source START I PDF/FRUS
  pairs.
- A known `doc_no`, `doc_key`, or comparison `row_id`; or a new PDF plus
  editor-supplied metadata.
- Poppler (`pdfinfo`, `pdftotext`, `pdftoppm`) and Tesseract for image-only PDFs.

The Bush Library PDFs in the matched START I set are image-only, so OCR is a
normal part of the process.

## Run A Known Pair

Use a page range when you already know the selected document pages. This is much
faster than OCRing an entire file-unit PDF.

```bash
python3 agent/start_i_frus_publication_agent.py \
  --doc-no 10 \
  --page-range 5-8 \
  --output-dir /tmp/frus-start-agent-d10
```

The output directory will contain:

- `publication-packet.json`: evidence ledger, page inventory, source-note model,
  draft body, and human-review warnings.
- `draft.md`: copy-readable FRUS-style draft packet.
- `draft.xml`: minimal TEI-like review stub.

## Run A New Source PDF

```bash
python3 agent/start_i_frus_publication_agent.py \
  --pdf path-or-url-to-bush-file-unit.pdf \
  --title "Memorandum From ..." \
  --source-note "Source: ..." \
  --page-range 12-15 \
  --output-dir /tmp/frus-start-agent-new-doc
```

For a new document, the page range and source note should come from the compiler
or source register. If they are missing, the agent will still inventory the PDF,
but it will mark the run as insufficient for a publication draft.

## Operating Spec

The instruction file for using this as a closed-network agent is:

```text
START_I_FRUS_PUBLICATION_AGENT.md
```

The reverse-engineered process data is:

```text
patterns/start_i_publication_process.json
```
