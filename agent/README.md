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

## START I Batch Run

The full START I PDF batch output is in:

```text
runs/start-i-pdfs/batch-summary.md
```

That batch ran all 17 exact-source START I PDFs through the universal agent in
full-PDF mode.

## Operating Spec

The universal instruction file is:

```text
FRUS_PUBLICATION_AGENT.md
```

The START I training profile is:

```text
patterns/start_i_publication_process.json
```
