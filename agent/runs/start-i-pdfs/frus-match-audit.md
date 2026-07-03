# START I Agent Output vs. Published FRUS Text Audit

Conclusion: the full-PDF batch outputs do not yet match the actual published FRUS documents as finished document text.

The outputs are useful file-unit OCR/review packets. They often contain some or much of the relevant FRUS text, but they also include extra archival/routing/source-file material, OCR errors, and combined material from PDFs that back multiple FRUS documents.

## Method

- `benchmark`: official FRUS HTML text from assets/data/frus-pdf-compare.json
- `candidate`: agent/runs/start-i-pdfs/*/publication-packet.json draft_body
- `normalization`: lowercase alphanumeric tokens; FRUS page breaks, tags, superscript footnote refs, and footnotes removed from benchmark
- `token_recall_pct`: share of official FRUS tokens found in the agent draft, counted as a bag of words
- `token_precision_pct`: share of agent draft tokens accounted for by the official FRUS text
- `phrase_coverage_pct`: exact coverage of sampled 8-token FRUS phrases in the agent draft; harsh because OCR errors break phrase matches

## Summary

- `pdf_outputs`: 17
- `frus_documents`: 25
- `mean_pdf_token_recall_pct`: 55.1
- `mean_pdf_token_precision_pct`: 40.1
- `mean_pdf_phrase_coverage_pct`: 39.2
- `pdfs_with_multiple_frus_documents`: 7
- `close_textual_match_count`: 0
- `contains_much_frus_text_count`: 2
- `does_not_match_count`: 15

## PDF-Level Results

| # | FRUS docs | actual tokens | draft tokens | draft/actual | token recall | token precision | phrase coverage | assessment |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 9, 10 | 2827 | 2734 | 0.97 | 61.5% | 63.6% | 45.3% | does_not_match_publication_text |
| 2 | 21 | 9467 | 3374 | 0.36 | 26.9% | 75.5% | 19.7% | does_not_match_publication_text |
| 3 | 23 | 1049 | 1120 | 1.07 | 19.4% | 18.2% | 0.0% | does_not_match_publication_text |
| 4 | 24 | 7842 | 12196 | 1.56 | 83.7% | 53.8% | 31.5% | does_not_match_publication_text |
| 5 | 25, 26 | 8045 | 1025 | 0.13 | 3.7% | 29.0% | 0.0% | does_not_match_publication_text |
| 6 | 27, 28 | 5957 | 7028 | 1.18 | 70.4% | 59.7% | 36.6% | does_not_match_publication_text |
| 7 | 31 | 484 | 1325 | 2.74 | 99.8% | 36.5% | 81.7% | does_not_match_publication_text |
| 8 | 32 | 7226 | 1711 | 0.24 | 6.0% | 25.1% | 0.0% | does_not_match_publication_text |
| 9 | 33 | 11521 | 453 | 0.04 | 1.8% | 46.8% | 0.0% | does_not_match_publication_text |
| 10 | 68 | 1827 | 449 | 0.25 | 4.3% | 17.4% | 0.0% | does_not_match_publication_text |
| 11 | 69, 70 | 2019 | 2497 | 1.24 | 87.2% | 70.5% | 65.9% | contains_much_frus_text_but_not_publication_ready |
| 12 | 86 | 554 | 20520 | 37.04 | 99.5% | 2.7% | 81.2% | does_not_match_publication_text |
| 13 | 115, 133, 140 | 1711 | 6069 | 3.55 | 82.4% | 23.2% | 56.8% | does_not_match_publication_text |
| 14 | 117, 119 | 1263 | 2704 | 2.14 | 97.1% | 45.4% | 89.8% | does_not_match_publication_text |
| 15 | 146 | 509 | 2985 | 5.86 | 99.6% | 17.0% | 96.8% | does_not_match_publication_text |
| 16 | 151 | 4619 | 4275 | 0.93 | 77.3% | 83.5% | 61.5% | contains_much_frus_text_but_not_publication_ready |
| 17 | 219, 220 | 2034 | 2351 | 1.16 | 16.1% | 14.0% | 0.0% | does_not_match_publication_text |

## Document-Level Results

| FRUS doc | PDF # | actual tokens | token recall | token precision | phrase coverage |
|---:|---:|---:|---:|---:|---:|
| 9 | 1 | 324 | 88.3% | 10.5% | 25.0% |
| 10 | 1 | 2503 | 65.3% | 59.8% | 47.8% |
| 21 | 2 | 9467 | 26.9% | 75.5% | 19.7% |
| 23 | 3 | 1049 | 19.4% | 18.2% | 0.0% |
| 24 | 4 | 7842 | 83.7% | 53.8% | 31.5% |
| 25 | 5 | 3302 | 7.0% | 22.5% | 0.0% |
| 26 | 5 | 4743 | 5.1% | 23.6% | 0.0% |
| 27 | 6 | 5714 | 70.8% | 57.6% | 37.5% |
| 28 | 6 | 243 | 90.5% | 3.1% | 10.0% |
| 31 | 7 | 484 | 99.8% | 36.5% | 81.7% |
| 32 | 8 | 7226 | 6.0% | 25.1% | 0.0% |
| 33 | 9 | 11521 | 1.8% | 46.8% | 0.0% |
| 68 | 10 | 1827 | 4.3% | 17.4% | 0.0% |
| 69 | 11 | 308 | 65.3% | 8.0% | 0.0% |
| 70 | 11 | 1711 | 98.1% | 67.2% | 77.0% |
| 86 | 12 | 554 | 99.5% | 2.7% | 81.2% |
| 115 | 13 | 670 | 60.6% | 6.7% | 0.0% |
| 133 | 13 | 480 | 98.8% | 7.8% | 88.3% |
| 140 | 13 | 561 | 99.6% | 9.2% | 97.1% |
| 117 | 14 | 106 | 68.9% | 2.7% | 0.0% |
| 119 | 14 | 1157 | 99.9% | 42.8% | 97.9% |
| 146 | 15 | 509 | 99.6% | 17.0% | 96.8% |
| 151 | 16 | 4619 | 77.3% | 83.5% | 61.5% |
| 219 | 17 | 991 | 26.1% | 11.0% | 0.0% |
| 220 | 17 | 1043 | 21.8% | 9.7% | 0.0% |

## Interpretation

- `token_recall` can be high even when a draft is not publication-ready, because OCR text may contain most names and words out of order or with noise.
- `token_precision` falls when the full-PDF run includes routing sheets, profile sheets, distribution records, or adjacent documents.
- `phrase_coverage` is the strictest signal; low values show that the OCR draft is not a clean transcription of the published FRUS document.
- Multi-document PDFs need document-specific page spans before the agent can produce one draft per FRUS document.
