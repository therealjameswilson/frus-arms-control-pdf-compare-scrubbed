const FRUS_COMPARE_DATA_URL = "./assets/data/frus-pdf-compare.json";

function compareEscapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function compactText(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function fileNameFromUrl(url) {
  try {
    return new URL(url).pathname.split("/").pop() || url;
  } catch {
    return url;
  }
}

function metadataRow(label, value, href) {
  if (!value) {
    return "";
  }
  const body = href
    ? `<a class="inline-link" href="${compareEscapeHtml(href)}" target="_blank" rel="noopener">${compareEscapeHtml(value)}</a>`
    : compareEscapeHtml(value);
  return `<div><dt>${compareEscapeHtml(label)}</dt><dd>${body}</dd></div>`;
}

function renderListItem(row, doc, selectedId) {
  const activeClass = row.id === selectedId ? " is-active" : "";
  return `<button type="button" class="compare-list-item${activeClass}" data-compare-id="${compareEscapeHtml(row.id)}">
    <span>${compareEscapeHtml(row.volume_id)} / d${compareEscapeHtml(row.doc_no)}</span>
    <strong>${compareEscapeHtml(doc.title || row.doc_title)}</strong>
    <small>${compareEscapeHtml(row.archive_title || fileNameFromUrl(row.pdf_url))}</small>
  </button>`;
}

function buildSearchText(row, doc) {
  return compactText([
    row.volume_id,
    row.doc_no,
    row.doc_title,
    row.archive_title,
    row.source_stem,
    row.source_note,
    row.source_system,
    row.match_basis,
    row.local_id,
    row.naid,
    doc.title,
    doc.source_note,
    doc.text_preview
  ].join(" "));
}

document.addEventListener("DOMContentLoaded", async () => {
  const filterInput = document.getElementById("compare-filter");
  const volumeSelect = document.getElementById("compare-volume");
  const sourceSelect = document.getElementById("compare-source");
  const status = document.getElementById("compare-status");
  const count = document.getElementById("compare-count");
  const list = document.getElementById("compare-list");
  const selectedVolume = document.getElementById("selected-volume");
  const selectedTitle = document.getElementById("selected-title");
  const selectedPdfLink = document.getElementById("selected-pdf-link");
  const selectedFrusLink = document.getElementById("selected-frus-link");
  const selectedRecordLink = document.getElementById("selected-record-link");
  const selectedMetadata = document.getElementById("selected-metadata");
  const pdfFrame = document.getElementById("pdf-frame");
  const pdfCaption = document.getElementById("pdf-caption");
  const frusCaption = document.getElementById("frus-caption");
  const frusDocument = document.getElementById("frus-document");

  if (!filterInput || !volumeSelect || !sourceSelect || !status || !count || !list || !pdfFrame || !frusDocument) {
    return;
  }

  let payload;
  let rows = [];
  let filteredRows = [];
  let selectedId = new URLSearchParams(window.location.search).get("id") || "";

  function populateSelects() {
    const volumes = [...new Set(rows.map((row) => row.volume_id))].sort();
    const sources = [...new Set(rows.map((row) => row.source_system).filter(Boolean))].sort();
    volumeSelect.insertAdjacentHTML(
      "beforeend",
      volumes.map((volume) => `<option value="${compareEscapeHtml(volume)}">${compareEscapeHtml(volume)}</option>`).join("")
    );
    sourceSelect.insertAdjacentHTML(
      "beforeend",
      sources.map((source) => `<option value="${compareEscapeHtml(source)}">${compareEscapeHtml(source)}</option>`).join("")
    );
  }

  function applyFilters() {
    const query = compactText(filterInput.value);
    const selectedVolumeValue = volumeSelect.value;
    const selectedSourceValue = sourceSelect.value;
    filteredRows = rows.filter((row) => {
      const matchesQuery = !query || row.searchText.includes(query);
      const matchesVolume = selectedVolumeValue === "all" || row.volume_id === selectedVolumeValue;
      const matchesSource = selectedSourceValue === "all" || row.source_system === selectedSourceValue;
      return matchesQuery && matchesVolume && matchesSource;
    });

    if (!filteredRows.some((row) => row.id === selectedId)) {
      selectedId = filteredRows[0]?.id || "";
    }
    renderList();
    renderSelected();
  }

  function renderList() {
    count.textContent = `${filteredRows.length} matched PDF row${filteredRows.length === 1 ? "" : "s"} shown.`;
    if (!filteredRows.length) {
      list.innerHTML = '<p class="empty-state">No comparison rows match the current filters.</p>';
      return;
    }
    list.innerHTML = filteredRows
      .map((row) => renderListItem(row, payload.documents[row.doc_key] || {}, selectedId))
      .join("");
  }

  function setLink(link, href, fallbackText) {
    if (!link) {
      return;
    }
    if (href) {
      link.href = href;
      link.removeAttribute("aria-disabled");
    } else {
      link.href = "#";
      link.setAttribute("aria-disabled", "true");
    }
    if (fallbackText) {
      link.textContent = fallbackText;
    }
  }

  function renderSelected() {
    const row = rows.find((item) => item.id === selectedId);
    if (!row) {
      selectedVolume.textContent = "No row selected";
      selectedTitle.textContent = "No comparison row selected";
      selectedMetadata.innerHTML = "";
      pdfFrame.removeAttribute("src");
      frusDocument.innerHTML = '<p class="empty-state">Select a row to load the FRUS document text.</p>';
      return;
    }

    const doc = payload.documents[row.doc_key] || {};
    const recordHref = row.landing_url || row.catalog_url || "";
    selectedVolume.textContent = `${row.volume_id} / Document ${row.doc_no}`;
    selectedTitle.textContent = doc.title || row.doc_title;
    setLink(selectedPdfLink, row.pdf_url, "Open PDF");
    setLink(selectedFrusLink, doc.url || row.frus_url, "Open FRUS");
    setLink(selectedRecordLink, recordHref, recordHref ? "Archive record" : "No archive record");
    selectedRecordLink.style.display = recordHref ? "" : "none";

    selectedMetadata.innerHTML = [
      metadataRow("FRUS URL", doc.url || row.frus_url, doc.url || row.frus_url),
      metadataRow("PDF title", row.archive_title || fileNameFromUrl(row.pdf_url)),
      metadataRow("PDF source", row.source_system),
      metadataRow("Match basis", row.match_basis),
      metadataRow("Preview source", row.preview_pdf_is_local ? "Local same-origin cache" : "Official remote PDF"),
      metadataRow("Source stem", row.source_stem),
      metadataRow("Local ID", row.local_id),
      metadataRow("NAID", row.naid, row.catalog_url),
      metadataRow("Query", row.query),
      metadataRow("Source note", row.source_note || doc.source_note)
    ].join("");

    pdfFrame.src = row.preview_pdf_url || row.pdf_url;
    pdfCaption.textContent = row.archive_title || fileNameFromUrl(row.pdf_url);
    frusCaption.textContent = doc.url || row.frus_url;
    frusDocument.innerHTML = doc.html || '<p class="empty-state">No FRUS text was extracted for this row.</p>';
    window.history.replaceState(null, "", `${window.location.pathname}?id=${encodeURIComponent(row.id)}`);
  }

  try {
    const response = await fetch(FRUS_COMPARE_DATA_URL);
    if (!response.ok) {
      throw new Error(`Unable to load ${FRUS_COMPARE_DATA_URL}`);
    }
    payload = await response.json();
    rows = (payload.comparisons || []).map((row) => ({
      ...row,
      searchText: buildSearchText(row, payload.documents[row.doc_key] || {})
    }));
    populateSelects();
    status.textContent = `${payload.summary.comparison_rows} exact-source PDF rows, ${payload.summary.frus_documents} FRUS documents, ${payload.summary.unique_pdf_urls} unique PDF URLs. ${payload.summary.excluded_direct_pdf_rows} broad candidate rows scrubbed.`;
    filteredRows = rows;
    if (!selectedId && rows.length) {
      selectedId = rows[0].id;
    }
    applyFilters();
  } catch (error) {
    status.textContent = "Comparison data could not be loaded.";
    list.innerHTML = '<p class="empty-state">The comparison JSON is missing or invalid.</p>';
    console.error(error);
    return;
  }

  filterInput.addEventListener("input", applyFilters);
  volumeSelect.addEventListener("change", applyFilters);
  sourceSelect.addEventListener("change", applyFilters);
  list.addEventListener("click", (event) => {
    const button = event.target.closest("[data-compare-id]");
    if (!button) {
      return;
    }
    selectedId = button.dataset.compareId;
    renderList();
    renderSelected();
  });
});
