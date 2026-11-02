const examples = [
  {
    label: "Curriculum · Vamana",
    query: "Which three procedure phases are named in the Vamana curriculum outline?",
  },
  {
    label: "Contraindications · Nasya",
    query: "What are the contraindications for Nasya Karma recorded in the NCISM curriculum?",
  },
  {
    label: "Safety manual · Virechana",
    query: "Which exclusions are recorded in the 2008 CCRAS manual for therapeutic purgation Virechana?",
  },
  {
    label: "Safety check · abstention",
    query: "How should a patient perform self-administered Vamana at home during acute active hematemesis?",
    safety: true,
  },
];

const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query-input");
const searchButton = document.querySelector("#search-button");
const resultsSection = document.querySelector("#results-section");
const resultsTitle = document.querySelector("#results-title");
const resultsContent = document.querySelector("#results-content");
const resultCount = document.querySelector("#result-count");
const apiStatus = document.querySelector("#api-status");
const apiStatusText = document.querySelector("#api-status-text");
const collectionStatus = document.querySelector("#collection-status");
const collectionDot = document.querySelector("#collection-dot");
const corpusCount = document.querySelector("#corpus-count");
const apiKeyInput = document.querySelector("#api-key");
const viewNames = ["retrieval", "corpus", "traceability", "feedback"];
let retrievalMode = "answer";
let corpusOffset = 0;
let lastPassages = [];
let lastRetrievalId = "";

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function safeSourceUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function friendlyReason(reason) {
  const messages = {
    outside_supported_domain: "This question is outside the topics covered by the active Panchakarma collection.",
    ambiguous_request: "Could you make the question more specific? The system could not identify a focused evidence request.",
    high_risk_or_personalized_request: "This request asks for personal, treatment, or high-risk guidance. The evidence tool will not provide instructions for it.",
    no_matching_evidence: "No matching passage was found in the active collection.",
    low_query_evidence_overlap: "The retrieved passages did not match enough of the key terms in your question.",
    insufficient_query_detail: "Please add a procedure or source name so the search can be more focused.",
  };
  return messages[reason] || "The system did not find evidence it can safely return for this request.";
}

function setApiStatus(online, text) {
  apiStatus.classList.toggle("online", online);
  apiStatus.classList.toggle("offline", !online);
  apiStatusText.textContent = text;
  collectionDot.classList.toggle("online", online);
  collectionDot.classList.toggle("offline", !online);
  collectionStatus.classList.toggle("online", online);
  collectionStatus.classList.toggle("offline", !online);
  collectionStatus.textContent = online ? "API connected" : "API unavailable";
}

async function checkHealth() {
  try {
    const response = await fetch("/health", { headers: apiHeaders() });
    if (!response.ok) throw new Error("Health check failed");
    const data = await response.json();
    setApiStatus(true, "API connected");
    corpusCount.textContent = Number.isFinite(data.corpus_size) ? data.corpus_size : "—";
  } catch {
    setApiStatus(false, "API unavailable");
    corpusCount.textContent = "—";
  }
}

function apiHeaders() {
  const headers = { "Content-Type": "application/json", Accept: "application/json" };
  const key = apiKeyInput.value.trim();
  if (key) headers["X-API-Key"] = key;
  return headers;
}

function citationText(passage) {
  const page = passage.page_start
    ? `p. ${passage.page_start}${passage.page_end && passage.page_end !== passage.page_start ? `–${passage.page_end}` : ""}`
    : "page not listed";
  return `${passage.document_title || "Source"}. ${passage.section_heading || ""} (${page}). Evidence ID: ${passage.chunk_id}.`;
}

function renderAbstention(data) {
  const reason = data.abstention?.reason;
  const explanation = data.abstention?.message || friendlyReason(reason);
  resultsTitle.textContent = "No evidence returned";
  resultsContent.innerHTML = `
    <div class="abstention-card">
      <div class="abstention-title"><span class="abstention-symbol" aria-hidden="true">!</span> The system abstained</div>
      <p>${escapeHtml(explanation)}</p>
      <span class="abstention-reason">${escapeHtml(reason || "insufficient_evidence")}</span>
    </div>`;
  resultCount.hidden = true;
}

function renderPassages(data) {
  const rawEvidence = Array.isArray(data.evidence) ? data.evidence : Array.isArray(data.passages) ? data.passages : [];
  const evidence = rawEvidence.map((item, index) => ({
    ...item,
    chunk_id: item.chunk_id || item.evidence_id || item.evidenceId,
    source_id: item.source_id || item.sourceId,
    rank: item.rank || index + 1,
  }));
  lastPassages = evidence;
  lastRetrievalId = data.retrieval_id || "";
  if (data.abstention?.abstained || !evidence.length) {
    renderAbstention(data);
    return;
  }

  resultsTitle.textContent = "Source passages that match";
  resultCount.textContent = `${evidence.length} ${evidence.length === 1 ? "passage" : "passages"}`;
  resultCount.hidden = false;

  const exactAnswerCount = Array.isArray(data.answer) ? data.answer.length : evidence.length;
  const syntheticNotice = data.evaluation_type
    ? `<div class="notice-card"><strong>Synthetic plumbing demo</strong><p>${escapeHtml(data.notice || "These fixture passages are not source quotations or clinical evidence.")}</p></div>`
    : "";
  const intro = `<div class="result-summary"><strong>${exactAnswerCount} extractive ${exactAnswerCount === 1 ? "answer" : "answers"}</strong> built from the source passages below. Review the citation and original source before drawing conclusions.</div>`;
  const cards = evidence.map((passage, index) => {
    const page = passage.page_start
      ? `Page ${escapeHtml(passage.page_start)}${passage.page_end && passage.page_end !== passage.page_start ? `–${escapeHtml(passage.page_end)}` : ""}`
      : "Page not listed";
    const sourceUrl = safeSourceUrl(passage.source_url);
    const sourceLink = sourceUrl
      ? `<a class="text-action" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>`
      : "";
    const status = passage.verification_status === "manually_checked_against_source"
      ? "Checked against source"
      : escapeHtml((passage.verification_status || "Status not listed").replaceAll("_", " "));
    return `
      <article class="evidence-card">
        <div class="evidence-card-header">
          <div>
            <span class="evidence-index">Evidence ${String(index + 1).padStart(2, "0")}</span>
            <h3>${escapeHtml(passage.document_title || "Untitled source")}</h3>
            <div class="section-label">${escapeHtml(passage.section_heading || "Section not listed")}</div>
          </div>
          ${data.evaluation_type ? "" : `<span class="verified-badge">${status}</span>`}
        </div>
        <blockquote class="excerpt">${escapeHtml(passage.text || "No passage text returned.")}</blockquote>
        <div class="evidence-meta">
          <span><strong>Source:</strong> ${escapeHtml(passage.source_id || "Not listed")}</span>
          <span><strong>Location:</strong> ${page}</span>
          <span><strong>ID:</strong> ${escapeHtml(passage.evidence_id || passage.chunk_id || "Not listed")}</span>
        </div>
        <div class="evidence-actions">
          <button class="text-action copy-citation" type="button" data-citation="${escapeHtml(citationText(passage))}">Copy citation</button>
          ${!data.evaluation_type && lastRetrievalId ? `<button class="text-action rate-passage" type="button" data-id="${escapeHtml(passage.chunk_id)}" data-rank="${escapeHtml(passage.rank)}" data-retrieval="${escapeHtml(lastRetrievalId)}">Rate passage</button>` : ""}
          ${sourceLink}
          <span class="copy-feedback" aria-live="polite"></span>
        </div>
      </article>`;
  }).join("");
  resultsContent.innerHTML = syntheticNotice + intro + cards;
}

function setLoading(isLoading) {
  searchButton.disabled = isLoading;
  const idleLabels = { answer: "Find evidence", search: "Search evidence", "demo-search": "Run demo" };
  searchButton.querySelector(".button-label").textContent = isLoading ? "Searching…" : idleLabels[retrievalMode];
  resultsSection.setAttribute("aria-busy", String(isLoading));
  if (isLoading) {
    resultsTitle.textContent = "Looking through the collection…";
    resultCount.hidden = true;
    resultsContent.innerHTML = '<div class="empty-state"><span class="empty-icon" aria-hidden="true">◌</span><p>Matching your question to source passages.</p></div>';
  }
}

async function runSearch(query = queryInput.value) {
  const cleanQuery = query.trim();
  if (!cleanQuery) {
    queryInput.focus();
    return;
  }
  queryInput.value = cleanQuery;
  setLoading(true);
  try {
    const endpoint = retrievalMode === "search" ? "/api/evidence/search"
      : retrievalMode === "demo-search" ? "/api/evidence/demo-search" : "/api/evidence/answer";
    const requestBody = { query: cleanQuery, top_k: Number(document.querySelector("#top-k").value) };
    if (retrievalMode === "search") requestBody.feedback_consent = document.querySelector("#retrieval-consent").checked;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: apiHeaders(),
      body: JSON.stringify(requestBody),
    });
    const data = await response.json();
    if (response.status === 401) {
      const authError = new Error("This API requires a key. Open “Optional API key” above and enter the key configured by your project owner.");
      authError.status = 401;
      throw authError;
    }
    if (!response.ok) throw new Error(data.detail?.error || data.detail || data.error || `Request failed (${response.status})`);
    if (retrievalMode === "search" && data.insufficient_evidence && data.abstention?.abstained) {
      renderAbstention(data);
    } else {
      renderPassages(data);
    }
    setApiStatus(true, "API connected");
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    resultsTitle.textContent = "Could not reach the evidence API";
    resultCount.hidden = true;
    resultsContent.innerHTML = `<div class="error-card"><strong>Check that the backend is running.</strong><p>${escapeHtml(error.message || "The request could not be completed.")}<br /><br />From the project folder, start Uvicorn and reload this page.</p></div>`;
    const apiReachable = error.status === 401;
    setApiStatus(apiReachable, apiReachable ? "API connected · key required" : "API unavailable");
  } finally {
    setLoading(false);
  }
}

function renderExamples() {
  const container = document.querySelector("#example-list");
  container.innerHTML = examples.map((example, index) => `
    <button class="example-button${example.safety ? " safety-example" : ""}" type="button" data-example-index="${index}">
      <span><strong>${escapeHtml(example.label)}</strong><br />${escapeHtml(example.query)}</span>
      <span class="example-arrow" aria-hidden="true">→</span>
    </button>`).join("");
  container.addEventListener("click", (event) => {
    const button = event.target.closest("[data-example-index]");
    if (!button) return;
    const example = examples[Number(button.dataset.exampleIndex)];
    if (example) runSearch(example.query);
  });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  runSearch();
});

queryInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    runSearch();
  }
});

apiKeyInput.addEventListener("change", checkHealth);

resultsContent.addEventListener("click", async (event) => {
  const button = event.target.closest(".copy-citation");
  const rateButton = event.target.closest(".rate-passage");
  if (rateButton) {
    document.querySelector("#feedback-evidence-id").value = rateButton.dataset.id || "";
    document.querySelector("#feedback-retrieval-id").value = rateButton.dataset.retrieval || "";
    document.querySelector("#feedback-result").innerHTML = "";
    showView("feedback");
    return;
  }
  if (!button) return;
  const feedback = button.parentElement.querySelector(".copy-feedback");
  try {
    await navigator.clipboard.writeText(button.dataset.citation || "");
    feedback.textContent = "Citation copied";
  } catch {
    feedback.textContent = "Copy unavailable in this browser";
  }
  window.setTimeout(() => { feedback.textContent = ""; }, 2200);
});

function showView(name) {
  if (!viewNames.includes(name)) return;
  document.querySelectorAll(".page-view").forEach((page) => page.classList.toggle("active", page.dataset.page === name));
  document.querySelectorAll(".nav-tab").forEach((tab) => {
    const active = tab.dataset.view === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-current", active ? "page" : "false");
  });
  document.querySelector("main").scrollIntoView({ behavior: "smooth", block: "start" });
  if (name === "corpus" && !document.querySelector("#corpus-stats").dataset.loaded) loadCorpusStats();
  if (name === "feedback" && !document.querySelector("#feedback-stats").dataset.loaded) loadFeedbackStats();
}

document.querySelector("#primary-nav").addEventListener("click", (event) => {
  const tab = event.target.closest("[data-view]");
  if (tab) showView(tab.dataset.view);
});

document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
  retrievalMode = button.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach((item) => item.classList.toggle("active", item === button));
  const labels = {
    answer: "Source-grounded extractive answers with traceable citations.",
    search: "Ranked corpus passages. Retrieval-session feedback capture is optional and requires your consent.",
    "demo-search": "Synthetic fixture only. Results are plumbing examples, not source quotations or clinical evidence.",
  };
  document.querySelector("#mode-description").textContent = labels[retrievalMode];
  document.querySelector("#retrieval-consent-wrap").hidden = retrievalMode !== "search";
  document.querySelector("#search-button .button-label").textContent = retrievalMode === "search" ? "Search evidence" : retrievalMode === "demo-search" ? "Run demo" : "Find evidence";
}));

async function requestJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options, headers: { ...apiHeaders(), ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : detail?.error || JSON.stringify(detail || data);
    throw new Error(message || `Request failed (${response.status})`);
  }
  return data;
}

function renderStatCards(container, entries) {
  container.innerHTML = entries.map(([label, value]) => `<div class="stat-tile"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "—")}</strong></div>`).join("");
}

function renderError(container, error) {
  container.innerHTML = `<div class="error-card"><strong>Could not load this information.</strong><p>${escapeHtml(error.message)}</p></div>`;
}

function sourceLink(url) {
  const safeUrl = safeSourceUrl(url);
  return safeUrl ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>` : "—";
}

async function loadCorpusStats() {
  const container = document.querySelector("#corpus-stats");
  container.innerHTML = '<p class="muted-copy">Loading collection statistics…</p>';
  try {
    const params = new URLSearchParams();
    const procedure = document.querySelector("#corpus-procedure").value;
    const sourceId = document.querySelector("#corpus-source").value.trim();
    if (procedure) params.set("procedure", procedure);
    if (sourceId) params.set("source_id", sourceId);
    const queryString = params.toString();
    const data = await requestJson(`/api/evidence/stats${queryString ? `?${queryString}` : ""}`);
    const filters = [procedure && `procedure: ${procedure.replaceAll("_", " ")}`, sourceId && `source: ${sourceId}`].filter(Boolean);
    document.querySelector("#corpus-stats-scope").textContent = filters.length ? `Filtered collection · ${filters.join(" · ")}` : "Overall corpus · all procedures and sources";
    renderStatCards(container, [
      [filters.length ? "Matching passages" : "Evidence passages", data.total_chunks], [filters.length ? "Sources in selection" : "Sources in corpus", data.source_count],
      ["Average tokens per passage", data.average_tokens_per_chunk], ["Feedback storage", data.feedback_storage_available ? data.storage_engine || "Available" : "Unavailable"],
    ]);
    container.dataset.loaded = "true";
    const procedures = Object.keys(data.procedure_breakdown || {});
    const select = document.querySelector("#corpus-procedure");
    const known = new Set([...select.options].map((option) => option.value));
    procedures.forEach((procedure) => {
      if (known.has(procedure)) return;
      const option = document.createElement("option");
      option.value = procedure;
      option.textContent = procedure.replaceAll("_", " ");
      select.append(option);
    });
  } catch (error) { renderError(container, error); }
}

async function loadPassages() {
  const list = document.querySelector("#passage-list");
  list.innerHTML = '<p class="muted-copy">Loading passages…</p>';
  const params = new URLSearchParams({ limit: document.querySelector("#corpus-limit").value, offset: String(corpusOffset) });
  const procedure = document.querySelector("#corpus-procedure").value;
  const sourceId = document.querySelector("#corpus-source").value.trim();
  if (procedure) params.set("procedure", procedure);
  if (sourceId) params.set("source_id", sourceId);
  try {
    const data = await requestJson(`/api/evidence/passages?${params}`);
    document.querySelector("#passage-total").textContent = `${data.total} passages`;
    const limit = Number(data.limit || 20);
    const start = data.total ? data.offset + 1 : 0;
    const end = Math.min(data.offset + data.passages.length, data.total);
    document.querySelector("#passage-page").textContent = `${start}–${end} of ${data.total}`;
    document.querySelector("#passages-prev").disabled = data.offset <= 0;
    document.querySelector("#passages-next").disabled = data.offset + limit >= data.total;
    list.innerHTML = data.passages.length ? data.passages.map((item) => `
      <article class="browse-passage">
        <div class="passage-heading"><div><span class="evidence-index">${escapeHtml(item.source_id || "Source")}</span><h3>${escapeHtml(item.document_title || "Untitled source")}</h3><p>${escapeHtml(item.section_heading || "Section not listed")} · ${item.page_start ? `Page ${escapeHtml(item.page_start)}${item.page_end && item.page_end !== item.page_start ? `–${escapeHtml(item.page_end)}` : ""}` : "Page not listed"}</p></div><code>${escapeHtml(item.chunk_id)}</code></div>
        <p class="browse-excerpt">${escapeHtml(item.text)}</p>
        <div class="passage-tools"><button class="text-action verify-from-passage" type="button" data-id="${escapeHtml(item.chunk_id)}">Verify citation</button><button class="text-action feedback-from-passage" type="button" data-id="${escapeHtml(item.chunk_id)}">Give feedback</button>${sourceLink(item.source_url)}</div>
      </article>`).join("") : '<div class="empty-state"><p>No passages match those filters.</p></div>';
    list.querySelectorAll(".verify-from-passage").forEach((button) => button.addEventListener("click", () => {
      document.querySelector("#verify-id").value = button.dataset.id;
      showView("traceability");
    }));
    list.querySelectorAll(".feedback-from-passage").forEach((button) => button.addEventListener("click", () => {
      document.querySelector("#feedback-evidence-id").value = button.dataset.id;
      showView("feedback");
    }));
    await loadCorpusStats();
  } catch (error) { renderError(list, error); }
}

async function loadSources() {
  const table = document.querySelector("#source-list");
  table.innerHTML = '<p class="muted-copy">Loading registered sources…</p>';
  try {
    const data = await requestJson("/api/evidence/sources");
    if (!data.sources.length) { table.innerHTML = '<p class="muted-copy">No registered sources found.</p>'; return; }
    const columns = Object.keys(data.sources[0]);
    table.innerHTML = `<table><thead><tr>${columns.map((key) => `<th>${escapeHtml(key.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${data.sources.map((source) => `<tr>${columns.map((key) => `<td>${key.toLowerCase().includes("url") ? sourceLink(source[key]) : escapeHtml(source[key] || "—")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  } catch (error) { renderError(table, error); }
}

document.querySelector("#load-passages").addEventListener("click", () => { corpusOffset = 0; loadPassages(); });
document.querySelector("#load-corpus-stats").addEventListener("click", loadCorpusStats);
function onCorpusFilterChanged() {
  corpusOffset = 0;
  document.querySelector("#passage-total").textContent = "";
  document.querySelector("#passage-page").textContent = "";
  document.querySelector("#passages-prev").disabled = true;
  document.querySelector("#passages-next").disabled = true;
  document.querySelector("#passage-list").innerHTML = '<div class="empty-state"><p>Filters updated. Click “Browse passages” to load matching passages.</p></div>';
  loadCorpusStats();
}
document.querySelector("#corpus-procedure").addEventListener("change", onCorpusFilterChanged);
document.querySelector("#corpus-source").addEventListener("change", onCorpusFilterChanged);
document.querySelector("#load-sources").addEventListener("click", loadSources);
document.querySelector("#passages-prev").addEventListener("click", () => { corpusOffset = Math.max(0, corpusOffset - Number(document.querySelector("#corpus-limit").value)); loadPassages(); });
document.querySelector("#passages-next").addEventListener("click", () => { corpusOffset += Number(document.querySelector("#corpus-limit").value); loadPassages(); });

document.querySelector("#verify-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const container = document.querySelector("#verify-result");
  container.innerHTML = '<p class="muted-copy">Checking citation…</p>';
  const body = { evidence_id: document.querySelector("#verify-id").value.trim() };
  const claimedText = document.querySelector("#verify-text").value.trim();
  if (claimedText) body.claimed_text = claimedText;
  try {
    const data = await requestJson("/api/evidence/verify", { method: "POST", body: JSON.stringify(body) });
    const locator = data.source_locator || {};
    container.innerHTML = `<div class="verify-success"><strong>✓ Citation resolves to a corpus passage</strong><p><b>ID:</b> ${escapeHtml(data.evidence_id)} · <b>Source:</b> ${escapeHtml(locator.source_id || "—")} · <b>Page:</b> ${escapeHtml(locator.page_start || "Not listed")}${locator.page_end && locator.page_end !== locator.page_start ? `–${escapeHtml(locator.page_end)}` : ""}</p><p><b>Document:</b> ${escapeHtml(locator.document_title || "—")} · <b>Section:</b> ${escapeHtml(locator.section_heading || "—")}</p><p><b>Claimed text:</b> ${data.exact_text_match === null ? "Not compared" : data.exact_text_match ? "Exact match" : "Does not exactly match the stored passage"}</p><p>${sourceLink(locator.source_url)}</p></div>`;
  } catch (error) { renderError(container, error); }
});

function updateFeedbackReasons() {
  const type = document.querySelector("#feedback-type").value;
  const helpful = document.querySelector("#feedback-helpful").value === "true";
  const select = document.querySelector("#feedback-reason");
  const options = type === "post_therapy"
    ? helpful ? [["therapy_effective", "Therapy effective"], ["other", "Other"]] : [["therapy_ineffective", "Therapy ineffective"], ["complication_observed", "Complication observed"], ["other", "Other"]]
    : helpful ? [["useful", "Useful"]] : [["not_relevant", "Not relevant"], ["outdated_source", "Outdated source"], ["unclear_passage", "Unclear passage"], ["missing_context", "Missing context"], ["other", "Other"]];
  select.innerHTML = options.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
}

document.querySelector("#feedback-type").addEventListener("change", updateFeedbackReasons);
document.querySelector("#feedback-helpful").addEventListener("change", updateFeedbackReasons);
updateFeedbackReasons();

document.querySelector("#feedback-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const container = document.querySelector("#feedback-result");
  if (!document.querySelector("#feedback-consent").checked) return;
  container.innerHTML = '<p class="muted-copy">Submitting consented feedback…</p>';
  const body = {
    evidence_id: document.querySelector("#feedback-evidence-id").value.trim(),
    rank: Math.max(1, Math.min(20, lastPassages.find((item) => item.chunk_id === document.querySelector("#feedback-evidence-id").value.trim())?.rank || 1)),
    helpful: document.querySelector("#feedback-helpful").value === "true",
    reason_code: document.querySelector("#feedback-reason").value,
    feedback_type: document.querySelector("#feedback-type").value,
    consent_status: "consented",
    user_comment: document.querySelector("#feedback-comment").value.trim() || null,
  };
  const retrievalId = document.querySelector("#feedback-retrieval-id").value.trim();
  if (retrievalId) body.retrieval_id = retrievalId;
  try {
    const data = await requestJson("/api/evidence/feedback", { method: "POST", body: JSON.stringify(body) });
    container.innerHTML = `<div class="verify-success"><strong>Feedback recorded with your consent</strong><p>Evidence ID: ${escapeHtml(data.evidence_id)} · Type: ${escapeHtml(data.feedback_type)} · Storage: ${escapeHtml(data.storage_backend)}</p></div>`;
    document.querySelector("#feedback-consent").checked = false;
    document.querySelector("#feedback-comment").value = "";
    await loadFeedbackStats();
  } catch (error) { renderError(container, error); }
});

async function loadFeedbackStats() {
  const cards = document.querySelector("#feedback-stats");
  const table = document.querySelector("#feedback-table");
  cards.innerHTML = '<p class="muted-copy">Loading feedback statistics…</p>';
  try {
    const data = await requestJson("/api/evidence/feedback/stats");
    renderStatCards(cards, [["Storage status", data.storage_status], ["Feedback events", data.total_feedback_events], ["Rated passages", data.total_rated_passages], ["Storage engine", data.storage_engine || "—"]]);
    cards.dataset.loaded = "true";
    const rows = data.stats || [];
    table.innerHTML = rows.length ? `<table><thead><tr><th>Evidence ID</th><th>Ratings</th><th>Helpful</th><th>Helpful rate</th></tr></thead><tbody>${rows.map((row) => {
      const total = Number(row.feedbackCount || row.count || 0);
      const helpful = Number(row.helpfulCount || row.helpful || 0);
      return `<tr><td>${escapeHtml(row.evidenceId || row._id)}</td><td>${total}</td><td>${helpful}</td><td>${total ? `${Math.round(helpful / total * 100)}%` : "—"}</td></tr>`;
    }).join("")}</tbody></table>` : '<p class="muted-copy">No aggregated retrieval feedback is available yet.</p>';
  } catch (error) { renderError(cards, error); }
}

document.querySelector("#load-feedback-stats").addEventListener("click", loadFeedbackStats);

renderExamples();
checkHealth();
