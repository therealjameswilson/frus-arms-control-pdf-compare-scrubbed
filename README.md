# FRUS Arms Control PDF Compare

Static GitHub Pages workbench for inspecting exact-source declassified PDFs beside the corresponding official FRUS document text.

Live site: https://therealjameswilson.github.io/frus-arms-control-pdf-compare/

Scope:

- `frus1981-88v44p1`
- `frus1989-92v31`

The site is generated from the local FRUS declassified PDF register and cached official FRUS EPUB text, then scrubbed to exact-source rows only. Reagan NSDD PDFs are included locally because Reagan Library PDF responses block cross-site iframe preview. Bush/NARA PDFs load from official public S3 URLs.

The deployable site is published from the `gh-pages` branch.
