# FRUS START I PDF Compare

Static GitHub Pages workbench for inspecting exact-source START I PDFs beside the corresponding official FRUS document text, 1989-1991.

Live site: https://therealjameswilson.github.io/frus-arms-control-pdf-compare-scrubbed/

Scope:

- `frus1989-92v31`

The site is generated from the local FRUS declassified PDF register and cached official FRUS EPUB text, then scrubbed to exact-source rows only. Bush/NARA PDFs load from official public S3 URLs.

The deployable site is published from the `gh-pages` branch.

## Universal Publication Agent

The `agent/` directory contains a universal FRUS Publication Agent trained from
the matched START I Bush PDF / FRUS document pairs. It can take other source
PDFs with compiler-supplied metadata, classify archival scaffolding pages,
select a document span, and emit a reviewable FRUS-style publication packet.
