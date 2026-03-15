/* ===================================================
  MIT License
  Author: Inari Solutions Sp. z o.o.
  Project notice: Demonstration code prepared for a hackathon.
  Production notice: This code is not ready for production use.
  File role: Frontend application logic with landing page transition.
  =================================================== */

const state = {
  conversationId: null,
  messages: [],
  pendingAssistantMessageIndex: -1,
  latestSearchUrl: "",
  latestSearchStatus: "",
  searchResultsRaw: [],
  searchResultsRows: [],
  searchFacets: [],
  selectedFacetValues: {},
  highlightedIds: new Set(),
  totalCount: 0,
  sortKey: "",
  sortOrder: "asc",
  nextMessageId: 1,
  lastAnimatedMessageId: 0,
  hasTransitioned: false,
  currentStep: 1,
};

/* ---------- DOM references ---------- */

const landingView = document.getElementById("landingView");
const appView = document.getElementById("appView");
const landingSearchForm = document.getElementById("landingSearchForm");
const landingSearchInput = document.getElementById("landingSearchInput");
const landingSearchBtn = document.getElementById("landingSearchBtn");
const backToLandingBtn = document.getElementById("backToLanding");

const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const applyFiltersBtn = document.getElementById("applyFiltersBtn");

const resultsSection = document.getElementById("resultsSection");
const filtersSection = document.getElementById("filtersSection");
const filtersWrapper = document.getElementById("filtersWrapper");
const resultsMetaNode = document.getElementById("resultsMeta");
const resultsCardsNode = document.getElementById("resultsCards");
const sortPillsNode = document.getElementById("sortPills");
const replySection = document.getElementById("replySection");
const replyContent = document.getElementById("replyContent");
const questionEcho = document.getElementById("questionEcho");
const questionEchoText = document.getElementById("questionEchoText");

const API_BASE = (window.__API_BASE__ || "").replace(/\/$/, "");
const FLAG_ICONS_BASE = "https://cdn.jsdelivr.net/gh/lipis/flag-icons@7.3.2/flags/4x3";

const SHOW_TOOL_EVENT_TOASTS = false;
const STREAM_PENDING_STATUSES = new Set(["Thinking..."]);

function buildApiUrl(path) {
  const normalizedPath = typeof path === "string" && path.startsWith("/") ? path : `/${path || ""}`;
  return `${API_BASE}${normalizedPath}`;
}

function ensureApiBase() {
  if (API_BASE) return;
  throw new Error("Frontend API is not configured. Set window.__API_BASE__ in frontend/config.js.");
}

/* ===================================================
   LANDING ↔ APP TRANSITION
   =================================================== */

function transitionToApp() {
  if (state.hasTransitioned) return;
  state.hasTransitioned = true;
  updateStepper(2);

  landingView.classList.add("landing-hidden");
  appView.classList.remove("app-view-hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      appView.classList.add("app-view-visible");
    });
  });
}

function transitionToLanding() {
  state.hasTransitioned = false;

  // Fade out app view first, then collapse after transition
  appView.classList.remove("app-view-visible");
  const onDone = () => {
    appView.removeEventListener("transitionend", onDone);
    appView.classList.add("app-view-hidden");
    landingView.classList.remove("landing-hidden");
  };
  appView.addEventListener("transitionend", onDone, { once: true });
  // Fallback in case transitionend doesn't fire
  setTimeout(onDone, 350);

  // Reset state for a fresh search
  state.conversationId = null;
  state.messages = [];
  state.pendingAssistantMessageIndex = -1;
  state.latestSearchUrl = "";
  state.latestSearchStatus = "";
  state.searchResultsRaw = [];
  state.searchResultsRows = [];
  state.searchFacets = [];
  state.selectedFacetValues = {};
  state.highlightedIds = new Set();
  state.totalCount = 0;
  state.sortKey = "";
  state.sortOrder = "asc";
  state.nextMessageId = 1;
  state.lastAnimatedMessageId = 0;
  state.currentStep = 1;

  if (replyContent) replyContent.innerHTML = "";
  if (replySection) replySection.classList.add("reply-hidden");
  if (resultsCardsNode) resultsCardsNode.innerHTML = "";
  hideResultsSection();
}

/* ===================================================
   PROGRESS STEPPER
   =================================================== */

function updateStepper(step) {
  state.currentStep = step;
  const el = document.getElementById("progressStepper");
  if (!el) return;
  el.querySelectorAll(".stepper-step").forEach((node) => {
    const n = parseInt(node.dataset.step, 10);
    node.classList.remove("stepper-step--completed", "stepper-step--active", "stepper-step--upcoming");
    if (n < step) node.classList.add("stepper-step--completed");
    else if (n === step) node.classList.add("stepper-step--active");
    else node.classList.add("stepper-step--upcoming");
  });
}

/* ===================================================
   CHAT RENDERING
   =================================================== */

function showToolNotification(toolName) {
  const toast = document.createElement("div");
  toast.className = "alert alert-info position-fixed";
  toast.style.right = "16px";
  toast.style.bottom = "16px";
  toast.style.zIndex = "1080";
  toast.style.margin = "0";
  toast.style.padding = "8px 12px";
  toast.textContent = `Tool triggered: ${toolName || "unknown"}`;
  document.body.appendChild(toast);
  window.setTimeout(() => toast.remove(), 2200);
}

function renderMarkdown(text) {
  if (typeof text !== "string" || !text.trim()) return "";

  const markedLib = window.marked;
  const domPurify = window.DOMPurify;
  if (!markedLib || !domPurify) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  markedLib.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });
  const rawHtml = markedLib.parse(text);
  return domPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: ["p", "br", "strong", "em", "code", "pre", "a", "ul", "ol", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"],
    ALLOWED_ATTR: ["href", "target", "rel"],
  });
}

function renderMessageBody(message) {
  const content = typeof message?.text === "string" ? message.text : "";
  if (!content) return "";
  if (message?.markdown) return renderMarkdown(content);
  return escapeHtml(content).replace(/\n/g, "<br>");
}

function renderConversation() {
  if (!replyContent || !replySection) return;

  const lastAssistant = [...state.messages].reverse().find((m) => m.role === "assistant") || null;
  const lastUser = [...state.messages].reverse().find((m) => m.role === "user") || null;

  if (questionEcho && questionEchoText) {
    if (lastUser && lastUser.text) {
      questionEchoText.textContent = lastUser.text;
      questionEcho.classList.remove("reply-hidden");
    } else {
      questionEcho.classList.add("reply-hidden");
    }
  }

  if (!lastAssistant || !lastAssistant.text) {
    replySection.classList.add("reply-hidden");
    return;
  }

  replySection.classList.remove("reply-hidden");
  replyContent.innerHTML = renderMessageBody(lastAssistant);
}

function appendMessage(role, text, markdown = false) {
  state.messages.push({ id: state.nextMessageId, role, text, markdown });
  state.nextMessageId += 1;
  return state.messages.length - 1;
}

function updateMessage(index, text) {
  if (!Number.isInteger(index) || index < 0 || index >= state.messages.length) return;
  state.messages[index].text = text;
}

/* ===================================================
   TEXT PROCESSING
   =================================================== */

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function pickText(value) {
  if (!value) return "";
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) {
    for (const entry of value) {
      const candidate = pickText(entry);
      if (candidate) return candidate;
    }
    return "";
  }
  if (typeof value === "object") {
    if (typeof value.en === "string" && value.en.trim()) return value.en.trim();
    if (typeof value.label === "string" && value.label.trim()) return value.label.trim();
    for (const nestedValue of Object.values(value)) {
      const candidate = pickText(nestedValue);
      if (candidate) return candidate;
    }
  }
  return "";
}

function pickFirstUrl(value) {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.startsWith("http") ? trimmed : "";
  }
  if (Array.isArray(value)) {
    for (const entry of value) {
      const found = pickFirstUrl(entry);
      if (found) return found;
    }
  }
  if (value && typeof value === "object") {
    for (const key of ["resource", "url", "uri", "href", "@id", "id"]) {
      const found = pickFirstUrl(value[key]);
      if (found) return found;
    }
  }
  return "";
}

function getFlagAssetCode(code) {
  if (typeof code !== "string") return "";
  const normalized = code.trim().toLowerCase();
  if (!normalized) return "";
  if (normalized === "eu") return "eu";
  if (!/^[a-z]{2}$/.test(normalized)) return "";
  return normalized;
}

function buildProvenanceFlagHtml(code) {
  const assetCode = getFlagAssetCode(code);
  if (!assetCode) return "";

  return `<img class="provenance-flag" src="${FLAG_ICONS_BASE}/${assetCode}.svg" alt="" aria-hidden="true" loading="lazy" decoding="async">`;
}

function pickProvenance(item) {
  const candidates = [
    item?.provenance,
    item?.country,
    item?.spatial,
    item?.spatial_coverage,
    item?.spatialCoverage,
  ];

  for (const candidate of candidates) {
    if (!candidate) continue;

    if (Array.isArray(candidate) && candidate.length > 0) {
      const first = candidate[0];
      if (first && typeof first === "object") {
        const id = typeof first.id === "string" ? first.id.trim().toLowerCase() : "";
        const title = pickText(first.title) || pickText(first.label) || "";
        if (id || title) return { id, title };
      }
      continue;
    }

    if (typeof candidate === "object") {
      const id = typeof candidate.id === "string" ? candidate.id.trim().toLowerCase() : "";
      const title = pickText(candidate.title) || pickText(candidate.label) || "";
      if (id || title) return { id, title };
      continue;
    }

    if (typeof candidate === "string") {
      const raw = candidate.trim();
      if (!raw) continue;
      if (/^[a-z]{2}$/i.test(raw)) return { id: raw.toLowerCase(), title: "" };
      return { id: "", title: raw };
    }
  }

  return { id: "", title: "" };
}

function normalizeRow(item) {
  const toIdString = (value) => {
    if (typeof value === "string") return value.trim();
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
    return "";
  };

  const titleRaw = item?.title || item?.label || item?.name || "Untitled dataset";
  const title = pickText(titleRaw) || "Untitled dataset";
  const titleEn = (titleRaw && typeof titleRaw === "object" && typeof titleRaw.en === "string")
    ? titleRaw.en
    : title;

  const publisher = pickText(item?.publisher || item?.catalog?.publisher || "");
  const license = pickText(item?.license || "");
  const datasetUrl = pickFirstUrl(item?.datasetUri || item?.dataset_url || item?.resource || item?.url || item?.uri || item?.landing_page || item?.identifier);
  const provenance = pickProvenance(item);

  const identifierFromArray = Array.isArray(item?.identifier)
    ? item.identifier.map((entry) => toIdString(entry) || pickText(entry)).find(Boolean) || ""
    : "";

  let datasetId =
    toIdString(item?.id)
    || toIdString(item?.datasetId)
    || toIdString(item?.dataset_id)
    || toIdString(item?.["@id"])
    || identifierFromArray
    || "";

  if (!datasetId && datasetUrl) {
    try {
      const parsedUrl = new URL(datasetUrl);
      const parts = parsedUrl.pathname.split("/").filter(Boolean);
      datasetId = parts.length > 0 ? decodeURIComponent(parts[parts.length - 1]) : "";
    } catch {
      datasetId = datasetUrl;
    }
  }

  const fileTypes = [];
  const distributions = Array.isArray(item?.distributions) ? item.distributions : [];
  for (const dist of distributions) {
    if (!dist || typeof dist !== "object") continue;
    for (const key of ["format", "type", "mediaType", "mimeType"]) {
      const text = pickText(dist[key]);
      if (text && !fileTypes.includes(text)) fileTypes.push(text);
    }
  }

  const resources = Array.isArray(item?.resources) ? item.resources : [];
  for (const resource of resources) {
    if (!resource || typeof resource !== "object") continue;
    for (const key of ["format", "type", "mediaType", "mimeType"]) {
      const text = pickText(resource[key]);
      if (text && !fileTypes.includes(text)) fileTypes.push(text);
    }
  }

  return {
    id: datasetId || "",
    title,
    title_en: titleEn || title,
    publisher,
    license,
    provenance_id: provenance.id,
    provenance_title: provenance.title,
    file_types: fileTypes,
    dataset_url: datasetUrl,
  };
}

/* ===================================================
   RESULTS TABLE RENDERING
   =================================================== */

function buildCardHtml(row) {
  const isHighlighted = state.highlightedIds.has(row.id);
  const cardClass = isHighlighted ? "result-card result-card--highlighted" : "result-card";
  const title = escapeHtml(row.title_en || row.title || "Untitled");
  const publisher = escapeHtml(row.publisher || "Unknown publisher");
  const datasetName = row.title_en || row.title || "Untitled";
  const provenanceCode = typeof row.provenance_id === "string" ? row.provenance_id.trim().toLowerCase() : "";
  const provenanceLabel = typeof row.provenance_title === "string" ? row.provenance_title.trim() : "";
  const hasAnyProvenance = Boolean(provenanceCode || provenanceLabel);
  const hasValidCountryCode = /^[a-z]{2}$/.test(provenanceCode);
  const provenanceFlagHtml = hasValidCountryCode ? buildProvenanceFlagHtml(provenanceCode) : "";
  const provenanceText = hasValidCountryCode
    ? (provenanceLabel || provenanceCode.toUpperCase())
    : "Others";

  const formatPills = row.file_types.length > 0
    ? row.file_types.map((fmt) => {
        const pillClass = isHighlighted ? "format-pill format-pill--highlighted" : "format-pill";
        return `<span class="${pillClass}">${escapeHtml(fmt)}</span>`;
      }).join("")
    : "";

  const provenanceHtml = hasAnyProvenance
    ? `<span class="provenance-pill" title="${escapeHtml(provenanceText)}">${[provenanceFlagHtml, escapeHtml(provenanceText)].filter(Boolean).join(" ")}</span>`
    : "";

  const urlHtml = row.dataset_url
    ? `<a href="${escapeHtml(row.dataset_url)}" target="_blank" rel="noopener" class="result-open-link">Open &#8599;</a>`
    : "";

  const starHtml = isHighlighted
    ? '<span class="result-star" title="AI recommended">&#9733;</span>'
    : "";

  return `
    <div class="${cardClass}" data-dataset-id="${escapeHtml(row.id)}" data-dataset-name="${escapeHtml(datasetName)}">
      <div class="result-card-header">
        <div class="result-card-title-wrap">
          <div class="result-card-title">${title}</div>
          <div class="result-card-publisher">${publisher}</div>
        </div>
        ${starHtml}
      </div>
      <div class="result-card-footer">
        <div class="result-card-formats">${provenanceHtml}${formatPills}</div>
        ${urlHtml}
      </div>
    </div>
  `;
}

function renderResultsTable() {
  if (!resultsCardsNode) return;

  const sortedRows = [...state.searchResultsRows].sort((left, right) => {
    if (!state.sortKey) return 0;
    const direction = state.sortOrder === "desc" ? -1 : 1;
    const toComparable = (row) => {
      if (state.sortKey === "highlight") return state.highlightedIds.has(row.id) ? 1 : 0;
      if (state.sortKey === "formats") return Array.isArray(row.file_types) ? row.file_types.join(", ").toLowerCase() : "";
      if (state.sortKey === "url") return typeof row.dataset_url === "string" ? row.dataset_url.toLowerCase() : "";
      if (state.sortKey === "title") return String(row.title_en || row.title || "").toLowerCase();
      return String(row[state.sortKey] || "").toLowerCase();
    };
    const a = toComparable(left);
    const b = toComparable(right);
    if (a < b) return -1 * direction;
    if (a > b) return 1 * direction;
    return 0;
  });

  if (state.highlightedIds.size === 0) {
    const cardsHtml = sortedRows.map(buildCardHtml).join("");
    resultsCardsNode.innerHTML = cardsHtml || '<p class="no-results-msg">No results for current filters.</p>';
    return;
  }

  const highlightedRows = sortedRows.filter(r => state.highlightedIds.has(r.id));
  const otherRows = sortedRows.filter(r => !state.highlightedIds.has(r.id));

  let html = "";

  if (highlightedRows.length > 0) {
    html += `<div class="results-section-header results-section-header--highlighted">
      <span class="results-section-icon">&#9733;</span>
      AI Recommended (${highlightedRows.length} dataset${highlightedRows.length !== 1 ? "s" : ""})
    </div>`;
    html += `<div class="results-cards-group">${highlightedRows.map(buildCardHtml).join("")}</div>`;
  }

  if (otherRows.length > 0) {
    html += `<div class="results-section-header results-section-header--other">
      Other results (${otherRows.length} dataset${otherRows.length !== 1 ? "s" : ""})
    </div>`;
    html += `<div class="results-cards-group">${otherRows.map(buildCardHtml).join("")}</div>`;
  }

  resultsCardsNode.innerHTML = html || '<p class="no-results-msg">No results for current filters.</p>';
}

function renderSortHeaders() {
  if (!sortPillsNode) return;
  const pills = sortPillsNode.querySelectorAll(".sort-pill");
  pills.forEach((pill) => {
    const key = pill.dataset.sortKey || "";
    pill.classList.toggle("sort-pill--active", state.sortKey === key);
    let arrow = "";
    if (state.sortKey === key) {
      arrow = state.sortOrder === "asc" ? " \u2191" : " \u2193";
    }
    const base = pill.textContent ? pill.textContent.replace(/\s[\u2191\u2193]$/, "") : "";
    pill.textContent = `${base}${arrow}`;
  });
}

function renderFilters() {
  if (!filtersSection) return;

  const formatFacetOptionText = (labelText, countText) => {
    const safeLabel = String(labelText || "").trim();
    const safeCount = String(countText || "");
    const maxLabelLength = 40;
    if (safeLabel.length <= maxLabelLength) return `${safeLabel}${safeCount}`;
    const headLength = 24;
    const tailLength = Math.max(0, maxLabelLength - headLength - 3);
    const head = safeLabel.slice(0, headLength);
    const tail = tailLength > 0 ? safeLabel.slice(-tailLength) : "";
    return `${head}...${tail}${safeCount}`;
  };

  if (!Array.isArray(state.searchFacets) || state.searchFacets.length === 0) {
    filtersSection.innerHTML = '<p class="results-meta mb-0">No facet filters available for this query.</p>';
    return;
  }

  const cards = state.searchFacets
    .filter((facet) => facet && typeof facet === "object" && Array.isArray(facet.items) && facet.items.length > 0)
    .map((facet) => {
      const facetId = facet.id || "unknown";
      const facetTitle = pickText(facet.title) || facetId;
      const selected = new Set(state.selectedFacetValues[facetId] || []);
      const options = facet.items
        .map((item) => {
          const value = typeof item?.id === "string" ? item.id : "";
          const label = pickText(item?.title) || value;
          const count = Number.isInteger(item?.count) ? ` (${item.count})` : "";
          const selectedAttr = selected.has(value) ? "selected" : "";
          const optionTitle = label + count;
          const optionText = formatFacetOptionText(label, count);
          return `<option value="${escapeHtml(value)}" title="${escapeHtml(optionTitle)}" ${selectedAttr}>${escapeHtml(optionText)}</option>`;
        })
        .join("");

      return `
        <div class="facet-card">
          <label class="facet-label" for="facet-${escapeHtml(facetId)}">${escapeHtml(facetTitle)}</label>
          <select id="facet-${escapeHtml(facetId)}" class="form-select facet-select" data-facet-id="${escapeHtml(facetId)}" multiple size="6">
            ${options}
          </select>
        </div>
      `;
    })
    .join("");

  filtersSection.innerHTML = `<div class="facet-grid">${cards}</div>`;

  filtersSection.querySelectorAll(".facet-select").forEach((selectNode) => {
    selectNode.addEventListener("change", (event) => {
      const target = event.currentTarget;
      const facetId = target?.dataset?.facetId || "";
      if (!facetId) return;
      const values = Array.from(target.selectedOptions || []).map((option) => option.value).filter(Boolean);
      state.selectedFacetValues[facetId] = values;
    });
  });
}

function renderResultsMeta() {
  if (!resultsMetaNode) return;
  resultsMetaNode.textContent = `${state.searchResultsRows.length} results`;
}

function ensureResultsVisible() {
  if (resultsSection) {
    resultsSection.classList.remove("results-hidden");
    resultsSection.classList.add("results-visible");
  }
  if (filtersWrapper) {
    filtersWrapper.classList.remove("filters-hidden");
    filtersWrapper.classList.add("filters-visible");
  }
  if (state.currentStep < 3) updateStepper(3);
}

function hideResultsSection() {
  if (resultsSection) {
    resultsSection.classList.remove("results-visible");
    resultsSection.classList.add("results-hidden");
  }
  if (filtersWrapper) {
    filtersWrapper.classList.remove("filters-visible");
    filtersWrapper.classList.add("filters-hidden");
  }
}

/* ===================================================
   SEARCH & API
   =================================================== */

function parseFacetsParam(urlInstance) {
  const rawFacets = urlInstance.searchParams.get("facets");
  if (!rawFacets) return {};

  const normalizeFacetsObject = (input) => {
    if (!input || typeof input !== "object") return {};
    const normalized = {};
    for (const [facetId, values] of Object.entries(input)) {
      if (!Array.isArray(values)) { normalized[facetId] = []; continue; }
      const cleanedValues = values
        .filter((value) => typeof value === "string")
        .map((value) => value.trim())
        .filter(Boolean)
        .map((value) => (facetId === "country" ? value.toLowerCase() : value));
      normalized[facetId] = cleanedValues;
    }
    return normalized;
  };

  try {
    return normalizeFacetsObject(JSON.parse(rawFacets));
  } catch {
    try {
      const maybeFixed = rawFacets
        .replace(/([{,]\s*)'([^']+)'\s*:/g, '$1"$2":')
        .replace(/:\s*'([^']*)'/g, ': "$1"');
      return normalizeFacetsObject(JSON.parse(maybeFixed));
    } catch {
      return {};
    }
  }
}

function buildSearchUrl(baseUrl, selectedFacetValues) {
  const targetUrl = new URL(baseUrl);
  targetUrl.searchParams.set("limit", "50");

  const facets = parseFacetsParam(targetUrl);
  const facetEntries = Object.entries(selectedFacetValues || {});
  for (const [facetId, values] of facetEntries) {
    facets[facetId] = Array.isArray(values)
      ? values.filter((v) => typeof v === "string").map((v) => v.trim()).filter(Boolean).map((v) => (facetId === "country" ? v.toLowerCase() : v))
      : [];
  }

  targetUrl.searchParams.set("facets", JSON.stringify(facets));
  return targetUrl.toString();
}

async function fetchSearchData(baseUrl) {
  if (!baseUrl) return;

  const requestUrl = buildSearchUrl(baseUrl, state.selectedFacetValues);
  const response = await fetch(requestUrl);
  if (!response.ok) throw new Error(`Search API call failed (${response.status}).`);

  const payload = await response.json();
  const result = payload && typeof payload === "object" ? (payload.result || payload) : {};

  const facets = Array.isArray(result.facets) ? result.facets : [];
  const rawResults = Array.isArray(result.results) ? result.results : [];

  state.totalCount = Number.isInteger(result.count) ? result.count : rawResults.length;
  state.searchFacets = facets;
  state.searchResultsRaw = rawResults;
  state.searchResultsRows = rawResults.map(normalizeRow);

  ensureResultsVisible();
  renderFilters();
  renderResultsTable();
  renderResultsMeta();
}

/* ===================================================
   STREAMING
   =================================================== */

function startSendButtonLoading() {
  if (!sendBtn.dataset.idleHtml) sendBtn.dataset.idleHtml = sendBtn.innerHTML;
  sendBtn.classList.add("is-loading");
}

function stopSendButtonLoading() {
  if (sendBtn.dataset.idleHtml) sendBtn.innerHTML = sendBtn.dataset.idleHtml;
  delete sendBtn.dataset.idleHtml;
  sendBtn.classList.remove("is-loading");
}

function setResultsInteractionLocked(isLocked) {
  if (!resultsCardsNode) return;
  resultsCardsNode.classList.toggle("results-cards--loading", Boolean(isLocked));
}

function setProcessingState(isProcessing) {
  if (isProcessing) startSendButtonLoading();
  else stopSendButtonLoading();
  setResultsInteractionLocked(isProcessing);
}

function parseSseBlock(block) {
  const lines = block.split("\n");
  let eventName = "message";
  const dataLines = [];

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) eventName = line.slice(6).trim() || "message";
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }

  const dataText = dataLines.join("\n");
  let data = null;
  if (dataText) {
    try { data = JSON.parse(dataText); }
    catch { data = { text: dataText }; }
  }

  return { eventName, data };
}

async function runStream(conversationId) {
  ensureApiBase();

  const response = await fetch(buildApiUrl("/stream"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId }),
  });

  if (!response.ok || !response.body) throw new Error("Stream request failed.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (!block.trim()) continue;

      const { eventName, data } = parseSseBlock(block);

      if (eventName === "chunk") {
        const chunkText = data && typeof data.text === "string" ? data.text : "";
        if (state.pendingAssistantMessageIndex >= 0) {
          const previous = state.messages[state.pendingAssistantMessageIndex]?.text || "";
          const nextText = STREAM_PENDING_STATUSES.has(previous.trim()) ? chunkText : previous + chunkText;
          updateMessage(state.pendingAssistantMessageIndex, nextText);
          renderConversation();
        }
        continue;
      }

      if (eventName === "done") {
        const finalText = data && typeof data.response === "string" ? data.response : "";
        if (finalText && state.pendingAssistantMessageIndex >= 0) {
          updateMessage(state.pendingAssistantMessageIndex, finalText);
          renderConversation();
        }
        continue;
      }

      if (eventName === "tool") {
        const toolName = data && typeof data.name === "string" ? data.name : "";
        if (SHOW_TOOL_EVENT_TOASTS) showToolNotification(toolName);
        continue;
      }

      if (eventName === "search_url") {
        const eventPayload = data && typeof data === "object" ? data : {};
        state.latestSearchUrl = typeof eventPayload.url === "string" ? eventPayload.url : "";
        state.latestSearchStatus = typeof eventPayload.status === "string" ? eventPayload.status : "info";
        if (state.latestSearchUrl) await fetchSearchData(state.latestSearchUrl);
        continue;
      }

      if (eventName === "ai_highlight") {
        const eventPayload = data && typeof data === "object" ? data : {};
        const ids = Array.isArray(eventPayload.ids)
          ? eventPayload.ids.filter((id) => typeof id === "string" && id.trim()).map((id) => id.trim())
          : [];
        state.highlightedIds = new Set(ids);
        if (typeof eventPayload.status === "string") state.latestSearchStatus = eventPayload.status;
        renderResultsTable();
        renderResultsMeta();
        continue;
      }

      if (eventName === "error") {
        const message = data && typeof data.message === "string" ? data.message : "Unknown stream error.";
        throw new Error(message);
      }
    }
  }
}

/* ===================================================
   SEND MESSAGE
   =================================================== */

function buildHiddenFiltersContext() {
  return {
    must_rerun_search: true,
    rerun_reason: "filters_changed",
    selected_facets: state.selectedFacetValues,
    search_url: state.latestSearchUrl,
    status: state.latestSearchStatus,
    count: state.totalCount,
  };
}

async function sendMessage(message, options = {}) {
  const includeHiddenFilters = Boolean(options.includeHiddenFilters);
  const isDatasetDetail = Boolean(options.datasetDetail);
  const messageForApi = includeHiddenFilters
    ? `${message}\n\n[MANDATORY_ACTION]\nrun search_dataset_window again with current filters before responding\n\n[INTERNAL_FILTER_CONTEXT_JSON]\n${JSON.stringify(buildHiddenFiltersContext())}`
    : message;

  // Transition to app view on first message
  transitionToApp();
  if (!isDatasetDetail) updateStepper(2);

  sendBtn.disabled = true;
  messageInput.disabled = true;
  if (applyFiltersBtn) applyFiltersBtn.disabled = true;

  setProcessingState(true);

  // Clear previous conversation for fresh query (keep table for dataset detail)
  state.messages = [];
  state.highlightedIds = new Set();
  state.nextMessageId = 1;
  state.lastAnimatedMessageId = 0;
  if (!isDatasetDetail) {
    if (resultsCardsNode) resultsCardsNode.innerHTML = "";
    hideResultsSection();
  }

  appendMessage("user", message, false);
  renderConversation();

  state.pendingAssistantMessageIndex = appendMessage("assistant", "Thinking...", true);
  renderConversation();

  try {
    ensureApiBase();

    const requestResponse = await fetch(buildApiUrl("/request"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: messageForApi,
        conversation_id: state.conversationId,
      }),
    });

    if (!requestResponse.ok) {
      if (state.pendingAssistantMessageIndex >= 0) {
        updateMessage(state.pendingAssistantMessageIndex, "Request failed while updating conversation.");
        renderConversation();
      }
      return;
    }

    const requestPayload = await requestResponse.json();
    state.conversationId = requestPayload.conversation_id || state.conversationId;
    await runStream(state.conversationId);
  } catch (error) {
    if (state.pendingAssistantMessageIndex >= 0) {
      updateMessage(
        state.pendingAssistantMessageIndex,
        error instanceof Error ? error.message : "Network error while processing request."
      );
      renderConversation();
    }
  } finally {
    state.pendingAssistantMessageIndex = -1;
    setProcessingState(false);
    sendBtn.disabled = false;
    messageInput.disabled = false;
    messageInput.focus();
    if (applyFiltersBtn) applyFiltersBtn.disabled = false;
  }
}

/* ===================================================
   EVENT HANDLERS
   =================================================== */

// Landing search form
landingSearchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = landingSearchInput.value.trim();
  if (!query) return;
  landingSearchBtn.disabled = true;
  landingSearchInput.value = "";
  await sendMessage(query);
  landingSearchBtn.disabled = false;
});

// Quick-start chip clicks
document.querySelectorAll(".search-chip").forEach((chip) => {
  chip.addEventListener("click", async () => {
    const query = chip.dataset.query;
    if (!query) return;
    landingSearchBtn.disabled = true;
    await sendMessage(query);
    landingSearchBtn.disabled = false;
  });
});

// Chat form (in app view)
chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const typedMessage = messageInput.value.trim();
  if (!typedMessage) return;
  messageInput.value = "";
  await sendMessage(typedMessage);
});

// Back to landing
backToLandingBtn.addEventListener("click", () => {
  transitionToLanding();
});

// Apply filters
applyFiltersBtn?.addEventListener("click", async () => {
  window.scrollTo({ top: 0, behavior: "smooth" });

  if (!state.latestSearchUrl) {
    appendMessage("assistant", "No search URL available yet. Ask AIDEEU first to generate results.", true);
    if (replySection) replySection.classList.remove("reply-hidden");
    renderConversation();
    return;
  }

  try {
    await fetchSearchData(state.latestSearchUrl);
  } catch (error) {
    appendMessage("assistant", error instanceof Error ? error.message : "Failed to apply frontend filters.", true);
    if (replySection) replySection.classList.remove("reply-hidden");
    renderConversation();
    return;
  }

  await sendMessage("Apply filters", { includeHiddenFilters: true });
});

// Sort pills
sortPillsNode?.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const pill = target.closest(".sort-pill");
  if (!pill) return;
  const nextKey = pill.dataset.sortKey || "";
  if (!nextKey) return;

  if (state.sortKey === nextKey) {
    state.sortOrder = state.sortOrder === "asc" ? "desc" : "asc";
  } else {
    state.sortKey = nextKey;
    state.sortOrder = "asc";
  }

  renderSortHeaders();
  renderResultsTable();
});

// Dataset card click
resultsCardsNode?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  // Don't intercept "Open" link clicks
  if (target.closest(".result-open-link")) return;

  const card = target.closest(".result-card");
  if (!card) return;

  updateStepper(4);
  event.preventDefault();
  if (sendBtn.disabled) return;

  window.scrollTo({ top: 0, behavior: "smooth" });

  const datasetId = (card.getAttribute("data-dataset-id") || "").trim();
  if (!datasetId) return;

  const datasetName = (card.getAttribute("data-dataset-name") || "Untitled").trim() || "Untitled";
  const followUpMessage = `Show me more details about ${datasetId} (${datasetName})`;
  await sendMessage(followUpMessage, { datasetDetail: true });
});

// Typewriter placeholder rotation for the landing search
const placeholders = [
  "How do EU countries rank on gender pay gap?",
  "Show me air pollution levels across European capitals",
  "What are municipal waste recycling rates in 2023?",
  "How much do EU spends on green procurement?"
];

let placeholderIndex = 0;
let charIndex = 0;
let isDeleting = false;
let typewriterTimeout = null;

function typewriterStep() {
  if (state.hasTransitioned || !landingSearchInput) return;

  const current = placeholders[placeholderIndex];

  if (!isDeleting) {
    charIndex++;
    landingSearchInput.placeholder = current.slice(0, charIndex);

    if (charIndex >= current.length) {
      typewriterTimeout = setTimeout(() => {
        isDeleting = true;
        typewriterStep();
      }, 2500);
      return;
    }
    typewriterTimeout = setTimeout(typewriterStep, 45 + Math.random() * 25);
  } else {
    charIndex--;
    landingSearchInput.placeholder = current.slice(0, charIndex);

    if (charIndex <= 0) {
      isDeleting = false;
      placeholderIndex = (placeholderIndex + 1) % placeholders.length;
      typewriterTimeout = setTimeout(typewriterStep, 400);
      return;
    }
    typewriterTimeout = setTimeout(typewriterStep, 20);
  }
}

// Pause typewriter on focus, resume on blur
landingSearchInput.addEventListener("focus", () => {
  clearTimeout(typewriterTimeout);
});

landingSearchInput.addEventListener("blur", () => {
  if (!landingSearchInput.value && !state.hasTransitioned) {
    typewriterTimeout = setTimeout(typewriterStep, 600);
  }
});

// Start typewriter after initial page load
typewriterTimeout = setTimeout(typewriterStep, 1500);

/* ---------- Scroll reveal for How It Works cards ---------- */
const howCards = document.querySelectorAll(".how-card");
if (howCards.length > 0 && "IntersectionObserver" in window) {
  howCards.forEach((card, i) => {
    card.style.animationDelay = `${i * 0.12}s`;
  });
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  howCards.forEach((card) => revealObserver.observe(card));
}

/* ---------- Count-up animation for stat values ---------- */
function animateCountUp(element, target, suffix, duration) {
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReduced) {
    element.textContent = target.toLocaleString() + suffix;
    return;
  }
  const start = performance.now();
  const update = (now) => {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(target * eased);
    element.textContent = current.toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(update);
  };
  requestAnimationFrame(update);
}

const statValues = document.querySelectorAll(".stat-value");
if (statValues.length >= 2 && "IntersectionObserver" in window) {
  const statObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          animateCountUp(statValues[0], 1, "M+", 1200);
          animateCountUp(statValues[1], 27, "", 1000);
          statObserver.disconnect();
        }
      });
    },
    { threshold: 0.5 }
  );
  statObserver.observe(statValues[0]);
}

/* ---------- Navbar scroll effect ---------- */
const navbarLanding = document.querySelector("#landingView .navbar");
if (navbarLanding) {
  window.addEventListener(
    "scroll",
    () => {
      navbarLanding.classList.toggle("navbar-scrolled", window.scrollY > 20);
    },
    { passive: true }
  );
}

/* ---------- Init ---------- */
renderConversation();
renderSortHeaders();
