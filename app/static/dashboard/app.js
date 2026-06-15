const state = {
  activeRunId: null,
  activeCandidateId: null,
  candidates: [],
  sourceStatuses: [],
  savedSearches: [],
  opportunities: [],
  decisionReports: {},
  comparableDetails: {},
  feedbackSummary: null,
  alerts: [],
  settings: null,
  interpretation: null,
  runs: [],
  loading: false,
};

const form = document.querySelector("#search-form");
const runButton = document.querySelector("#run-search");
const interpretButton = document.querySelector("#interpret-search");
const analyzePromoteButton = document.querySelector("#analyze-promote-listing");
const saveButton = document.querySelector("#save-search");
const saveSettingsButton = document.querySelector("#save-settings");
const resetButton = document.querySelector("#reset-form");
const showOverpriced = document.querySelector("#show-overpriced");
const showHidden = document.querySelector("#show-hidden");
const refreshHistory = document.querySelector("#refresh-history");
const refreshSavedSearches = document.querySelector("#refresh-saved-searches");
const refreshOpportunities = document.querySelector("#refresh-opportunities");
const refreshAlerts = document.querySelector("#refresh-alerts");
const alertRegion = document.querySelector("#alert-region");
const listEl = document.querySelector("#opportunity-list");
const historyEl = document.querySelector("#run-history");
const savedSearchesEl = document.querySelector("#saved-searches");
const opportunitiesEl = document.querySelector("#opportunities");
const alertsEl = document.querySelector("#alerts");
const pilotFeedbackSummaryEl = document.querySelector("#pilot-feedback-summary");
const detailEl = document.querySelector("#candidate-detail");
const detailTitle = document.querySelector("#detail-title");
const detailSourceLink = document.querySelector("#detail-source-link");
const sourceStatusPanel = document.querySelector("#source-status-panel");
const interpretedFiltersEl = document.querySelector("#interpreted-filters");

const defaults = {
  name: "Civic shortlist",
  natural_language_query: "2020 Honda Civic Montreal",
  make: "Honda",
  model: "Civic",
  year_min: "2020",
  year_max: "",
  price_max_cad: "",
  mileage_max_km: "",
  location_city: "Montreal",
  location_province: "QC",
  radius_km: "50",
  listing_limit: "25",
  sources: "both",
  max_candidates: "10",
  scheduled: false,
  alerts_enabled: false,
  in_app_alerts_enabled: true,
  email_alerts_enabled: false,
  schedule_cron: "daily",
  listing_url: "",
  vin: "",
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await runSearch();
});

resetButton.addEventListener("click", () => {
  Object.entries(defaults).forEach(([key, value]) => {
    const input = document.querySelector(`#${key}`);
    if (!input) return;
    if (input.type === "checkbox") {
      input.checked = Boolean(value);
    } else {
      input.value = value;
    }
  });
  clearAlert();
});

saveButton.addEventListener("click", saveCurrentSearch);
interpretButton.addEventListener("click", previewInterpretation);
saveSettingsButton.addEventListener("click", async (event) => {
  event.preventDefault();
  event.stopPropagation();
  await saveSettings();
});
analyzePromoteButton.addEventListener("click", analyzeAndPromoteListing);
showOverpriced.addEventListener("change", renderCandidates);
showHidden.addEventListener("change", renderCandidates);
refreshHistory.addEventListener("click", loadHistory);
refreshSavedSearches.addEventListener("click", loadSavedSearches);
refreshOpportunities.addEventListener("click", loadOpportunities);
refreshAlerts.addEventListener("click", loadAlerts);

loadSettings();
loadAlerts();
loadOpportunities();
loadPilotFeedbackSummary();
loadSavedSearches();
loadHistory();
renderCandidates();

async function runSearch() {
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch("/api/searches/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload()),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Search failed"));
    state.interpretation = {
      interpreted_filters: body.interpreted_filters || {},
      applied_filters: body.normalized_filters || {},
      interpretation: body.interpretation || {},
    };
    renderInterpretation();
    state.activeRunId = body.run_id;
    await loadHistory();
    if (body.run_id) {
      await loadRun(body.run_id);
    } else {
      state.candidates = body.ranked_opportunities || [];
      state.sourceStatuses = body.source_statuses || [];
      renderCandidates();
      renderSourceStatuses();
      updateSummary();
    }
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function previewInterpretation() {
  setLoading(true);
  clearAlert();
  try {
    const payload = buildPayload();
    const response = await fetch("/api/searches/interpret", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        natural_language_query: payload.natural_language_query,
        structured_filters: payload.structured_filters,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not interpret search"));
    state.interpretation = body;
    renderInterpretation();
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function saveCurrentSearch() {
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch("/api/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...buildPayload(),
        include_overpriced: showOverpriced.checked,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not save search"));
    await loadSavedSearches();
    showAlert(`Saved search: ${body.name}`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadSettings() {
  try {
    const response = await fetch("/api/settings");
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load settings"));
    state.settings = body;
    renderSettings();
    applySettingsDefaults(body);
  } catch (error) {
    showAlert(error.message);
  }
}

async function saveSettings() {
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch("/api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settingsPayload()),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not save settings"));
    state.settings = body;
    renderSettings();
    applySettingsDefaults(body);
    showAlert("Dealer settings saved.");
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function analyzeAndPromoteListing() {
  const listingUrl = value("listing_url");
  if (!listingUrl) {
    showAlert("Paste a Kijiji or AutoTrader listing URL before using Analyze + Promote.");
    return;
  }
  setLoading(true);
  clearAlert();
  try {
    const payload = buildPayload();
    const response = await fetch("/api/opportunities/from-listing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: payload.name || "Single listing intake",
        listing_url: payload.listing_url,
        vin: payload.vin,
        sources: payload.sources,
        listing_limit: payload.listing_limit,
        location_city: payload.structured_filters.location_city || "Montreal",
        location_province: payload.structured_filters.location_province || "QC",
        radius_km: payload.structured_filters.radius_km || 50,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not analyze and promote listing"));
    state.activeRunId = body.run_id;
    state.activeCandidateId = body.candidate_id;
    await Promise.all([loadOpportunities(), loadHistory()]);
    if (body.run_id) await loadRun(body.run_id);
    showAlert(`Promoted listing to opportunity ${shortId(body.opportunity?.id)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

function buildPayload() {
  return {
    name: value("name") || "Ad hoc search",
    natural_language_query: value("natural_language_query") || null,
    structured_filters: {
      make: value("make") || null,
      model: value("model") || null,
      year_min: numberValue("year_min"),
      year_max: numberValue("year_max"),
      price_max_cad: numberValue("price_max_cad"),
      mileage_max_km: numberValue("mileage_max_km"),
      location_city: value("location_city") || null,
      location_province: value("location_province") || null,
      radius_km: numberValue("radius_km"),
    },
    listing_limit: numberValue("listing_limit") || 25,
    sources: value("sources") || "both",
    max_candidates: numberValue("max_candidates") || 10,
    scheduled: document.querySelector("#scheduled").checked,
    schedule_cron: value("schedule_cron") || null,
    alerts_enabled: document.querySelector("#alerts_enabled").checked,
    in_app_alerts_enabled: document.querySelector("#in_app_alerts_enabled").checked,
    email_alerts_enabled: document.querySelector("#email_alerts_enabled").checked,
    listing_url: value("listing_url") || null,
    vin: value("vin") || null,
  };
}

function settingsPayload() {
  return {
    target_profit_cad: numberValue("setting_target_profit_cad") ?? 0,
    risk_tolerance: value("setting_risk_tolerance") || "medium",
    preferred_brands: csvTerms(value("setting_preferred_brands")),
    preferred_models: csvTerms(value("setting_preferred_models")),
    default_search_radius_km: numberValue("setting_default_search_radius_km") ?? 50,
    include_overpriced_default: document.querySelector("#setting_include_overpriced_default").checked,
    candidate_score_threshold: numberValue("setting_candidate_score_threshold") ?? 75,
    max_candidate_count: numberValue("setting_max_candidate_count") ?? 50,
    max_images_per_candidate: numberValue("setting_max_images_per_candidate") ?? 10,
  };
}

function renderSettings() {
  const settings = state.settings;
  if (!settings) return;
  setValue("setting_target_profit_cad", settings.target_profit_cad ?? 2500);
  setValue("setting_risk_tolerance", settings.risk_tolerance || "medium");
  setValue("setting_preferred_brands", (settings.preferred_brands || []).join(", "));
  setValue("setting_preferred_models", (settings.preferred_models || []).join(", "));
  setValue("setting_default_search_radius_km", settings.default_search_radius_km ?? 50);
  setValue("setting_candidate_score_threshold", settings.candidate_score_threshold ?? 75);
  setValue("setting_max_candidate_count", settings.max_candidate_count ?? 50);
  setValue("setting_max_images_per_candidate", settings.max_images_per_candidate ?? 10);
  document.querySelector("#setting_include_overpriced_default").checked = Boolean(settings.include_overpriced_default);
}

function applySettingsDefaults(settings) {
  if (!settings) return;
  defaults.radius_km = String(settings.default_search_radius_km ?? 50);
  defaults.max_candidates = String(settings.max_candidate_count ?? 10);
  setValue("radius_km", value("radius_km") || defaults.radius_km);
  setValue("max_candidates", value("max_candidates") || defaults.max_candidates);
  showOverpriced.checked = Boolean(settings.include_overpriced_default);
}

async function loadAlerts() {
  try {
    const response = await fetch("/api/alerts?limit=20");
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load alerts"));
    state.alerts = body.alerts || [];
    renderAlerts();
  } catch (error) {
    showAlert(error.message);
  }
}

async function loadSavedSearches() {
  try {
    const response = await fetch("/api/searches");
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load saved searches"));
    state.savedSearches = body.searches || [];
    renderSavedSearches();
  } catch (error) {
    showAlert(error.message);
  }
}

function renderInterpretation() {
  const interpretation = state.interpretation;
  if (!interpretation) {
    interpretedFiltersEl.innerHTML = "";
    return;
  }
  const applied = interpretation.applied_filters || {};
  const inferred = interpretation.interpreted_filters || {};
  const details = interpretation.interpretation || {};
  const keys = [
    "make",
    "model",
    "year_min",
    "year_max",
    "price_min_cad",
    "price_max_cad",
    "mileage_max_km",
    "location_city",
    "location_province",
    "radius_km",
    "seller_type",
  ];
  const appliedItems = keys
    .filter((key) => applied[key] !== null && applied[key] !== undefined && applied[key] !== "")
    .map((key) => `${filterLabel(key)}: ${filterValue(key, applied[key])}`);
  const inferredItems = keys
    .filter((key) => inferred[key] !== null && inferred[key] !== undefined && inferred[key] !== "")
    .map((key) => `${filterLabel(key)}: ${filterValue(key, inferred[key])}`);
  interpretedFiltersEl.innerHTML = `
    <div class="interpretation-card">
      <div class="detail-row">
        <strong>Interpreted filters</strong>
        <span>${Math.round(Number(details.confidence || 0) * 100)}%</span>
      </div>
      <div class="filter-chip-row">
        ${(appliedItems.length ? appliedItems : ["No applied filters"]).map((item) => `<span class="filter-chip">${escapeHtml(item)}</span>`).join("")}
      </div>
      <p class="meta-row">Inferred: ${escapeHtml(inferredItems.join(", ") || "none")}</p>
    </div>
  `;
}

async function loadOpportunities() {
  try {
    const response = await fetch("/api/opportunities");
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load opportunities"));
    state.opportunities = body.opportunities || [];
    renderOpportunities();
  } catch (error) {
    showAlert(error.message);
  }
}

async function loadPilotFeedbackSummary() {
  try {
    const response = await fetch("/api/feedback/summary");
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load pilot feedback summary"));
    state.feedbackSummary = body;
    renderPilotFeedbackSummary();
  } catch (error) {
    showAlert(error.message);
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/api/searches/runs");
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load run history"));
    state.runs = body.runs || [];
    renderHistory();
  } catch (error) {
    showAlert(error.message);
  }
}

async function promoteCandidate(candidateId) {
  if (!state.activeRunId || !candidateId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(
      `/api/searches/runs/${encodeURIComponent(state.activeRunId)}/candidates/${encodeURIComponent(candidateId)}/promote`,
      { method: "POST" }
    );
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not promote candidate"));
    const updatedCandidate = body.candidate || {};
    state.candidates = state.candidates.map((candidate) =>
      candidate.id === candidateId
        ? { ...candidate, selected: true, opportunity_id: body.id || updatedCandidate.opportunity_id }
        : candidate
    );
    state.activeCandidateId = candidateId;
    await loadOpportunities();
    renderCandidates();
    await loadCandidate(candidateId);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function updateOpportunityStage(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const stageInput = opportunitiesEl.querySelector(`[data-opportunity-stage="${cssEscape(opportunityId)}"]`);
    const overrideInput = opportunitiesEl.querySelector(`[data-ready-visit-override="${cssEscape(opportunityId)}"]`);
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/stage`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        stage: stageInput?.value || "new",
        override_missing_data_warning: Boolean(overrideInput?.checked),
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not update opportunity stage"));
    upsertOpportunity(body);
    if (body.latest_report) state.decisionReports[opportunityId] = body.latest_report;
    renderOpportunities();
    if (body.stage_update_warning) {
      showAlert("Ready to Visit needs missing key data resolved or an explicit override.");
    }
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function updateOpportunityContact(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const statusInput = opportunitiesEl.querySelector(`[data-opportunity-contact="${cssEscape(opportunityId)}"]`);
    const notesInput = opportunitiesEl.querySelector(`[data-opportunity-notes="${cssEscape(opportunityId)}"]`);
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/contact`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seller_contact_status: statusInput?.value || null,
        seller_notes: notesInput?.value.trim() || null,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not update opportunity contact"));
    upsertOpportunity(body);
    if (body.latest_report) state.decisionReports[opportunityId] = body.latest_report;
    renderOpportunities();
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function generateOpportunityReport(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/reports`, {
      method: "POST",
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not generate decision report"));
    state.decisionReports[opportunityId] = body;
    setLatestReportOnOpportunity(opportunityId, body);
    renderOpportunities();
    if (body.html_url) window.open(body.html_url, "_blank", "noreferrer");
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function openLatestOpportunityReport(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/reports/latest`);
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load latest decision report"));
    state.decisionReports[opportunityId] = body;
    setLatestReportOnOpportunity(opportunityId, body);
    renderOpportunities();
    if (body.html_url) window.open(body.html_url, "_blank", "noreferrer");
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function updateOpportunityChecklist(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const patch = {};
    checklistItems().forEach((item) => {
      const input = opportunitiesEl.querySelector(
        `[data-opportunity-checklist="${cssEscape(opportunityId)}"][data-checklist-key="${item.key}"]`
      );
      if (input) patch[item.key] = Boolean(input.checked);
    });
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/visit-checklist`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not update visit checklist"));
    upsertOpportunity(body);
    if (body.latest_report) state.decisionReports[opportunityId] = body.latest_report;
    renderOpportunities();
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function submitOpportunityFeedback(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        usefulness_rating: numberFromData("feedback-usefulness", opportunityId) || 3,
        accuracy_rating: numberFromData("feedback-accuracy", opportunityId) || 3,
        dealer_decision: valueFromData("feedback-decision", opportunityId) || "undecided",
        missing_info: listFromData("feedback-missing", opportunityId),
        incorrect_info: listFromData("feedback-incorrect", opportunityId),
        notes: valueFromData("feedback-notes", opportunityId) || null,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not save feedback"));
    await loadPilotFeedbackSummary();
    showAlert(`Saved feedback for opportunity ${shortId(opportunityId)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function uploadOpportunityDocument(opportunityId) {
  if (!opportunityId) return;
  const fileInput = opportunitiesEl.querySelector(`[data-document-file="${cssEscape(opportunityId)}"]`);
  const typeInput = opportunitiesEl.querySelector(`[data-document-type="${cssEscape(opportunityId)}"]`);
  const notesInput = opportunitiesEl.querySelector(`[data-document-notes="${cssEscape(opportunityId)}"]`);
  const file = fileInput?.files?.[0];
  if (!file) {
    showAlert("Choose a document file before uploading.");
    return;
  }

  setLoading(true);
  clearAlert();
  try {
    const formData = new FormData();
    formData.append("document_type", typeInput?.value || "seller_document");
    formData.append("file", file);
    if (notesInput?.value.trim()) formData.append("notes", notesInput.value.trim());

    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/documents`, {
      method: "POST",
      body: formData,
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not upload document"));
    upsertOpportunity(body.opportunity);
    if (body.opportunity?.latest_report) state.decisionReports[opportunityId] = body.opportunity.latest_report;
    renderOpportunities();
    showAlert(`Uploaded ${body.document?.document_label || "document"} for opportunity ${shortId(opportunityId)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function submitTitleEvidence(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/title-evidence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_type: valueFromData("title-source", opportunityId) || "manual",
        title_clearance_status: valueFromData("title-status", opportunityId) || "unknown",
        provider: valueFromData("title-provider", opportunityId) || null,
        lookup_reference: valueFromData("title-reference", opportunityId) || null,
        document_id: valueFromData("title-document", opportunityId) || null,
        seller_name: valueFromData("title-seller", opportunityId) || null,
        registered_owner_name: valueFromData("title-owner", opportunityId) || null,
        ownership_verified: checkboxFromData("title-ownership-verified", opportunityId),
        lienholder_name: valueFromData("title-lienholder", opportunityId) || null,
        lien_amount_cad: numberFromData("title-lien-amount", opportunityId),
        payout_required: checkboxFromData("title-payout-required", opportunityId),
        payout_amount_cad: numberFromData("title-payout-amount", opportunityId),
        payout_due_date: valueFromData("title-payout-due", opportunityId) || null,
        payout_status: valueFromData("title-payout-status", opportunityId) || "unknown",
        notes: valueFromData("title-notes", opportunityId) || null,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not save title evidence"));
    upsertOpportunity(body.opportunity);
    if (body.opportunity?.latest_report) state.decisionReports[opportunityId] = body.opportunity.latest_report;
    renderOpportunities();
    showAlert(`Saved title evidence for opportunity ${shortId(opportunityId)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function submitRecallCompliance(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/recall-compliance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_type: valueFromData("recall-source", opportunityId) || "manual",
        recall_status: valueFromData("recall-status", opportunityId) || "unknown",
        compliance_status: valueFromData("compliance-status", opportunityId) || "unknown",
        provider: valueFromData("recall-provider", opportunityId) || null,
        lookup_reference: valueFromData("recall-reference", opportunityId) || null,
        document_id: valueFromData("recall-document", opportunityId) || null,
        campaign_number: valueFromData("recall-campaign", opportunityId) || null,
        campaign_description: valueFromData("recall-description", opportunityId) || null,
        remedy_status: valueFromData("recall-remedy", opportunityId) || "unknown",
        completion_date: valueFromData("recall-completion-date", opportunityId) || null,
        import_country: valueFromData("import-country", opportunityId) || null,
        import_form: valueFromData("import-form", opportunityId) || null,
        riv_case_number: valueFromData("riv-case", opportunityId) || null,
        inspection_required: checkboxFromData("inspection-required", opportunityId),
        inspection_deadline: valueFromData("inspection-deadline", opportunityId) || null,
        notes: valueFromData("recall-notes", opportunityId) || null,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not save recall/compliance evidence"));
    upsertOpportunity(body.opportunity);
    if (body.opportunity?.latest_report) state.decisionReports[opportunityId] = body.opportunity.latest_report;
    renderOpportunities();
    showAlert(`Saved recall/compliance evidence for opportunity ${shortId(opportunityId)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function submitWholesaleEvidence(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/wholesale-evidence`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_type: valueFromData("wholesale-source", opportunityId) || "manual",
        provider: valueFromData("wholesale-provider", opportunityId) || null,
        lookup_reference: valueFromData("wholesale-reference", opportunityId) || null,
        document_id: valueFromData("wholesale-document", opportunityId) || null,
        region: valueFromData("wholesale-region", opportunityId) || null,
        wholesale_low_cad: numberFromData("wholesale-low", opportunityId),
        wholesale_avg_cad: numberFromData("wholesale-avg", opportunityId),
        wholesale_high_cad: numberFromData("wholesale-high", opportunityId),
        trade_in_value_cad: numberFromData("trade-in-value", opportunityId),
        retail_value_cad: numberFromData("wholesale-retail", opportunityId),
        auction_sale_low_cad: numberFromData("auction-sale-low", opportunityId),
        auction_sale_avg_cad: numberFromData("auction-sale-avg", opportunityId),
        auction_sale_high_cad: numberFromData("auction-sale-high", opportunityId),
        bid_count: integerFromData("bid-count", opportunityId),
        bidder_count: integerFromData("bidder-count", opportunityId),
        high_bid_cad: numberFromData("high-bid", opportunityId),
        sale_price_cad: numberFromData("sale-price", opportunityId),
        reserve_price_cad: numberFromData("reserve-price", opportunityId),
        condition_grade: valueFromData("condition-grade", opportunityId) || "unknown",
        condition_score: numberFromData("condition-score", opportunityId),
        condition_notes: valueFromData("condition-notes", opportunityId) || null,
        buyer_fee_cad: numberFromData("buyer-fee", opportunityId),
        transport_estimate_cad: numberFromData("wholesale-transport", opportunityId),
        reconditioning_estimate_cad: numberFromData("wholesale-recon", opportunityId),
        notes: valueFromData("wholesale-notes", opportunityId) || null,
      }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not save wholesale evidence"));
    upsertOpportunity(body.opportunity);
    if (body.opportunity?.latest_report) state.decisionReports[opportunityId] = body.opportunity.latest_report;
    renderOpportunities();
    showAlert(`Saved wholesale evidence for opportunity ${shortId(opportunityId)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function submitDealerCorrection(opportunityId) {
  if (!opportunityId) return;
  const corrections = [];
  const trim = valueFromData("correction-trim", opportunityId);
  const mileage = integerFromData("correction-mileage", opportunityId);
  const accidentStatus = valueFromData("correction-accident-status", opportunityId);
  const lienStatus = valueFromData("correction-lien-status", opportunityId);
  const reason = valueFromData("correction-reason", opportunityId) || null;

  if (trim) {
    corrections.push({ entity_type: "vehicle", field_name: "trim", new_value: trim });
  }
  if (mileage !== null) {
    corrections.push({ entity_type: "vehicle", field_name: "mileage_km", new_value: mileage });
  }
  if (accidentStatus) {
    corrections.push({ entity_type: "history", field_name: "accident_history_status", new_value: accidentStatus });
  }
  if (lienStatus) {
    corrections.push({ entity_type: "title", field_name: "lien_status", new_value: lienStatus });
  }
  if (!corrections.length) {
    showAlert("Enter at least one correction before saving.");
    return;
  }

  setLoading(true);
  clearAlert();
  try {
    let latestBody = null;
    for (const correction of corrections) {
      const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/corrections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...correction, reason }),
      });
      const body = await parseJson(response);
      if (!response.ok) throw new Error(errorMessage(body, "Could not save dealer correction"));
      latestBody = body;
    }
    if (latestBody?.opportunity) {
      upsertOpportunity(latestBody.opportunity);
      if (latestBody.opportunity.latest_report) {
        state.decisionReports[opportunityId] = latestBody.opportunity.latest_report;
      }
    }
    renderOpportunities();
    showAlert(`Saved ${corrections.length} correction${corrections.length === 1 ? "" : "s"} for opportunity ${shortId(opportunityId)}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadOpportunityComparables(opportunityId) {
  if (!opportunityId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/opportunities/${encodeURIComponent(opportunityId)}/comparables`);
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load comparables"));
    state.comparableDetails[opportunityId] = body;
    state.opportunities = state.opportunities.map((opportunity) =>
      opportunity.id === opportunityId ? { ...opportunity, comparables: body } : opportunity
    );
    renderOpportunities();
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function removeComparable(comparableId, opportunityId) {
  if (!comparableId || !opportunityId) return;
  const reasonInput = opportunitiesEl.querySelector(`[data-comparable-reason="${cssEscape(comparableId)}"]`);
  const reason = reasonInput?.value.trim() || "Dealer removed bad comparable";
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/comparables/${encodeURIComponent(comparableId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ included: false, excluded_reason: reason }),
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not remove comparable"));
    state.comparableDetails[opportunityId] = body;
    state.opportunities = state.opportunities.map((opportunity) =>
      opportunity.id === opportunityId
        ? {
            ...opportunity,
            comparables: body,
            candidate: {
              ...(opportunity.candidate || {}),
              pricing_summary: body.pricing_summary || opportunity.candidate?.pricing_summary || {},
              max_buy_price_cad: body.pricing_summary?.max_buy_price_cad ?? opportunity.candidate?.max_buy_price_cad,
              estimated_retail_value_cad: body.pricing_summary?.retail_mid_cad ?? opportunity.candidate?.estimated_retail_value_cad,
            },
            latest_report: body.report || opportunity.latest_report,
          }
        : opportunity
    );
    if (body.report) state.decisionReports[opportunityId] = body.report;
    renderOpportunities();
    showAlert(`Removed comparable and generated report v${body.report?.version || "-"}.`);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function runSavedSearch(searchId) {
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/searches/${encodeURIComponent(searchId)}/run`, {
      method: "POST",
    });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Saved search run failed"));
    state.activeRunId = body.run_id;
    await Promise.all([loadSavedSearches(), loadHistory()]);
    if (body.run_id) await loadRun(body.run_id);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadRun(runId) {
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(`/api/searches/runs/${encodeURIComponent(runId)}`);
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load run"));
    state.activeRunId = body.id;
    state.candidates = body.ranked_opportunities || [];
    state.sourceStatuses = body.source_statuses || [];
    state.activeCandidateId = state.candidates[0]?.id || null;
    renderHistory();
    renderCandidates();
    renderSourceStatuses();
    showSourceFailureAlert();
    updateSummary(body);
    if (state.activeCandidateId) {
      await loadCandidate(state.activeCandidateId);
    } else {
      renderEmptyDetail();
    }
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

async function loadCandidate(candidateId) {
  if (!state.activeRunId) return;
  clearAlert();
  try {
    const response = await fetch(
      `/api/searches/runs/${encodeURIComponent(state.activeRunId)}/candidates/${encodeURIComponent(candidateId)}`
    );
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not load candidate"));
    state.activeCandidateId = candidateId;
    renderCandidates();
    renderCandidateDetail(body);
  } catch (error) {
    showAlert(error.message);
  }
}

async function updateCandidateWorkflow(candidateId, patch) {
  if (!state.activeRunId || !candidateId) return;
  setLoading(true);
  clearAlert();
  try {
    const response = await fetch(
      `/api/searches/runs/${encodeURIComponent(state.activeRunId)}/candidates/${encodeURIComponent(candidateId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }
    );
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not update candidate"));
    state.activeCandidateId = candidateId;
    state.candidates = state.candidates.map((candidate) =>
      candidate.id === candidateId ? { ...candidate, ...body } : candidate
    );
    renderCandidates();
    renderCandidateDetail(body);
  } catch (error) {
    showAlert(error.message);
  } finally {
    setLoading(false);
  }
}

function renderOpportunities() {
  if (!state.opportunities.length) {
    opportunitiesEl.innerHTML = `<div class="promoted-card"><h3>No opportunities</h3><p class="meta-row">Promote selected candidates to track them here.</p></div>`;
    return;
  }

  opportunitiesEl.innerHTML = state.opportunities
    .map((opportunity) => {
      const candidate = opportunity.candidate || {};
      const title = candidate.title || "Promoted opportunity";
      const missingFields = (opportunity.missing_key_data || []).filter(Boolean);
      const shouldShowOverride = opportunity.stage === "ready_to_visit" && missingFields.length > 0;
      const report = state.decisionReports[opportunity.id] || opportunity.latest_report;
      return `
        <div class="promoted-card" data-opportunity-id="${escapeAttr(opportunity.id)}">
          <h3>${escapeHtml(title)}</h3>
          <div class="detail-row">
            <span>${escapeHtml(stageLabel(opportunity.stage || "new"))}</span>
            <span>${escapeHtml(candidate.source || "source")}</span>
          </div>
          <div class="detail-row">
            <span>${money(candidate.asking_price_cad)}</span>
            <span>Score ${score(opportunity.deal_score)}</span>
          </div>
          <div class="opportunity-control-group comparable-editing-group">
            <span class="field-label">Comparables</span>
            ${comparableSummaryHtml(opportunity)}
            <button type="button" class="secondary" data-load-opportunity-comparables="${escapeAttr(opportunity.id)}">Edit Comparables</button>
            ${comparableEditorHtml(opportunity)}
          </div>
          ${readinessWarningHtml(opportunity)}
          <div class="opportunity-control-group">
            <label class="field">
              <span>Stage</span>
              <select data-opportunity-stage="${escapeAttr(opportunity.id)}">
                ${stageOptions(opportunity.stage)}
              </select>
            </label>
            <label class="toggle ready-visit-override${shouldShowOverride ? "" : " hidden"}" data-ready-visit-override-row="${escapeAttr(opportunity.id)}">
              <input type="checkbox" data-ready-visit-override="${escapeAttr(opportunity.id)}" />
              <span>Override missing data</span>
            </label>
            <button type="button" data-update-opportunity-stage="${escapeAttr(opportunity.id)}">Save Stage</button>
          </div>
          <div class="opportunity-control-group">
            <label class="field">
              <span>Contact status</span>
              <select data-opportunity-contact="${escapeAttr(opportunity.id)}">
                ${contactStatusOptions(opportunity.seller_contact_status)}
              </select>
            </label>
            <label class="field">
              <span>Seller notes</span>
              <textarea data-opportunity-notes="${escapeAttr(opportunity.id)}" maxlength="5000">${escapeHtml(opportunity.seller_notes || "")}</textarea>
            </label>
            <button type="button" class="secondary" data-update-opportunity-contact="${escapeAttr(opportunity.id)}">Save Contact</button>
          </div>
          <div class="opportunity-control-group">
            <span class="field-label">Visit checklist</span>
            <div class="checklist-grid">
              ${checklistHtml(opportunity)}
            </div>
            <button type="button" class="secondary" data-update-opportunity-checklist="${escapeAttr(opportunity.id)}">Save Checklist</button>
          </div>
          <div class="opportunity-control-group dealer-corrections-group">
            <span class="field-label">Dealer corrections</span>
            ${dealerCorrectionSummaryHtml(opportunity)}
            ${dealerCorrectionFormHtml(opportunity)}
            <button type="button" class="secondary" data-submit-dealer-correction="${escapeAttr(opportunity.id)}">Save Corrections</button>
          </div>
          <div class="opportunity-control-group document-upload-group">
            <span class="field-label">Documents</span>
            ${documentSummaryHtml(opportunity)}
            <label class="field">
              <span>Type</span>
              <select data-document-type="${escapeAttr(opportunity.id)}">
                ${documentTypeOptions()}
              </select>
            </label>
            <label class="field">
              <span>File</span>
              <input type="file" data-document-file="${escapeAttr(opportunity.id)}" accept="application/pdf,image/jpeg,image/png,image/webp,text/plain" />
            </label>
            <label class="field">
              <span>Notes</span>
              <textarea data-document-notes="${escapeAttr(opportunity.id)}" maxlength="1000"></textarea>
            </label>
            <button type="button" class="secondary" data-upload-opportunity-document="${escapeAttr(opportunity.id)}">Upload Document</button>
          </div>
          <div class="opportunity-control-group title-evidence-group">
            <span class="field-label">Lien/title evidence</span>
            ${titleEvidenceSummaryHtml(opportunity)}
            ${titleEvidenceFormHtml(opportunity)}
            <button type="button" class="secondary" data-submit-title-evidence="${escapeAttr(opportunity.id)}">Save Title Evidence</button>
          </div>
          <div class="opportunity-control-group recall-compliance-group">
            <span class="field-label">Recall/compliance</span>
            ${recallComplianceSummaryHtml(opportunity)}
            ${recallComplianceFormHtml(opportunity)}
            <button type="button" class="secondary" data-submit-recall-compliance="${escapeAttr(opportunity.id)}">Save Recall Evidence</button>
          </div>
          <div class="opportunity-control-group wholesale-evidence-group">
            <span class="field-label">Wholesale/trade-in evidence</span>
            ${wholesaleEvidenceSummaryHtml(opportunity)}
            ${wholesaleEvidenceFormHtml(opportunity)}
            <button type="button" class="secondary" data-submit-wholesale-evidence="${escapeAttr(opportunity.id)}">Save Wholesale Evidence</button>
          </div>
          <div class="report-actions">
            <button type="button" data-generate-opportunity-report="${escapeAttr(opportunity.id)}">Generate Report</button>
            <button type="button" class="secondary" data-open-opportunity-report="${escapeAttr(opportunity.id)}">Open Latest</button>
          </div>
          ${report ? `<p class="meta-row">Report v${report.version} ${escapeHtml(report.status || "")}</p>` : `<p class="meta-row">No report generated</p>`}
          <div class="opportunity-control-group">
            <span class="field-label">Pilot feedback</span>
            ${feedbackFormHtml(opportunity)}
            <button type="button" class="secondary" data-submit-opportunity-feedback="${escapeAttr(opportunity.id)}">Save Feedback</button>
          </div>
        </div>
      `;
    })
    .join("");

  opportunitiesEl.querySelectorAll("[data-opportunity-stage]").forEach((select) => {
    select.addEventListener("change", () => {
      const opportunityId = select.dataset.opportunityStage;
      const row = opportunitiesEl.querySelector(`[data-ready-visit-override-row="${cssEscape(opportunityId)}"]`);
      const opportunity = state.opportunities.find((item) => item.id === opportunityId);
      const hasMissingData = Boolean(opportunity?.missing_key_data?.length);
      row?.classList.toggle("hidden", select.value !== "ready_to_visit" || !hasMissingData);
    });
  });
  opportunitiesEl.querySelectorAll("[data-update-opportunity-stage]").forEach((button) => {
    button.addEventListener("click", () => updateOpportunityStage(button.dataset.updateOpportunityStage));
  });
  opportunitiesEl.querySelectorAll("[data-update-opportunity-contact]").forEach((button) => {
    button.addEventListener("click", () => updateOpportunityContact(button.dataset.updateOpportunityContact));
  });
  opportunitiesEl.querySelectorAll("[data-update-opportunity-checklist]").forEach((button) => {
    button.addEventListener("click", () => updateOpportunityChecklist(button.dataset.updateOpportunityChecklist));
  });
  opportunitiesEl.querySelectorAll("[data-load-opportunity-comparables]").forEach((button) => {
    button.addEventListener("click", () => loadOpportunityComparables(button.dataset.loadOpportunityComparables));
  });
  opportunitiesEl.querySelectorAll("[data-remove-comparable]").forEach((button) => {
    button.addEventListener("click", () => removeComparable(button.dataset.removeComparable, button.dataset.comparableOpportunity));
  });
  opportunitiesEl.querySelectorAll("[data-upload-opportunity-document]").forEach((button) => {
    button.addEventListener("click", () => uploadOpportunityDocument(button.dataset.uploadOpportunityDocument));
  });
  opportunitiesEl.querySelectorAll("[data-submit-title-evidence]").forEach((button) => {
    button.addEventListener("click", () => submitTitleEvidence(button.dataset.submitTitleEvidence));
  });
  opportunitiesEl.querySelectorAll("[data-submit-recall-compliance]").forEach((button) => {
    button.addEventListener("click", () => submitRecallCompliance(button.dataset.submitRecallCompliance));
  });
  opportunitiesEl.querySelectorAll("[data-submit-wholesale-evidence]").forEach((button) => {
    button.addEventListener("click", () => submitWholesaleEvidence(button.dataset.submitWholesaleEvidence));
  });
  opportunitiesEl.querySelectorAll("[data-submit-dealer-correction]").forEach((button) => {
    button.addEventListener("click", () => submitDealerCorrection(button.dataset.submitDealerCorrection));
  });
  opportunitiesEl.querySelectorAll("[data-generate-opportunity-report]").forEach((button) => {
    button.addEventListener("click", () => generateOpportunityReport(button.dataset.generateOpportunityReport));
  });
  opportunitiesEl.querySelectorAll("[data-open-opportunity-report]").forEach((button) => {
    button.addEventListener("click", () => openLatestOpportunityReport(button.dataset.openOpportunityReport));
  });
  opportunitiesEl.querySelectorAll("[data-submit-opportunity-feedback]").forEach((button) => {
    button.addEventListener("click", () => submitOpportunityFeedback(button.dataset.submitOpportunityFeedback));
  });
}

function renderPilotFeedbackSummary() {
  const summary = state.feedbackSummary;
  if (!summary || summary.total_feedback === 0) {
    pilotFeedbackSummaryEl.innerHTML = `<div class="promoted-card"><h3>No pilot feedback</h3><p class="meta-row">Submit feedback after testing a report.</p></div>`;
    return;
  }
  pilotFeedbackSummaryEl.innerHTML = `
    <div class="promoted-card">
      <div class="data-grid">
        ${dataItem("Feedback", String(summary.total_feedback))}
        ${dataItem("Opportunities", String(summary.tested_opportunities))}
        ${dataItem("Usefulness", summary.average_usefulness ?? "-")}
        ${dataItem("Accuracy", summary.average_accuracy ?? "-")}
      </div>
      <div class="feedback-summary-block">
        <strong>Decisions</strong>
        ${tagList(Object.entries(summary.decision_counts || {}).map(([key, count]) => `${key}: ${count}`))}
      </div>
      <div class="feedback-summary-block">
        <strong>Missing info</strong>
        ${tagList((summary.common_missing_info || []).map((item) => `${item.value}: ${item.count}`))}
      </div>
    </div>
  `;
}

function renderSavedSearches() {
  if (!state.savedSearches.length) {
    savedSearchesEl.innerHTML = `<div class="saved-search-card"><h3>No saved searches</h3><p class="meta-row">Save the current form to reuse it.</p></div>`;
    return;
  }

  savedSearchesEl.innerHTML = state.savedSearches
    .map((search) => {
      const filters = search.structured_filters || {};
      const subtitle = [
        filters.year_min,
        filters.make,
        filters.model,
        filters.location_city || search.location_city,
      ].filter(Boolean).join(" ");
      return `
        <div class="saved-search-card" data-saved-search-card="${escapeHtml(search.id)}">
          <h3>${escapeHtml(search.name || "Saved search")}</h3>
          <div class="detail-row">
            <span>${escapeHtml(subtitle || search.natural_language_query || "Saved search")}</span>
            <span>${escapeHtml(search.sources || "both")}</span>
          </div>
          <div class="detail-row">
            <span>${search.max_candidates || 50} candidates</span>
            <span>${search.last_run_at ? `Last ${dateLabel(search.last_run_at)}` : "Never run"}</span>
          </div>
          <div class="detail-row">
            <span>${search.scheduled ? "Scheduled" : "Manual"}</span>
            <span>${escapeHtml(search.schedule_cron || "daily")}</span>
          </div>
          <div class="detail-row">
            <span>${search.alerts_enabled ? "Alerts on" : "Alerts off"}</span>
            <span>${alertChannelLabel(search)}</span>
          </div>
          <div class="saved-search-actions">
            <button type="button" class="secondary" data-select-saved-search="${escapeHtml(search.id)}">Select</button>
            <button type="button" data-run-saved-search="${escapeHtml(search.id)}">Run</button>
          </div>
        </div>
      `;
    })
    .join("");

  savedSearchesEl.querySelectorAll("[data-select-saved-search]").forEach((button) => {
    button.addEventListener("click", () => selectSavedSearch(button.dataset.selectSavedSearch));
  });
  savedSearchesEl.querySelectorAll("[data-run-saved-search]").forEach((button) => {
    button.addEventListener("click", () => runSavedSearch(button.dataset.runSavedSearch));
  });
}

function renderAlerts() {
  if (!state.alerts.length) {
    alertsEl.innerHTML = `<div class="saved-search-card"><h3>No alerts</h3><p class="meta-row">Saved-search alerts will appear here.</p></div>`;
    return;
  }

  alertsEl.innerHTML = state.alerts
    .map((alert) => {
      const metadata = alert.metadata || {};
      const unread = alert.status === "unread" ? " unread" : "";
      return `
        <div class="alert-card${unread}" data-alert-card="${escapeHtml(alert.id)}">
          <div class="detail-row">
            <strong>${escapeHtml(alert.title || "Alert")}</strong>
            <span>${escapeHtml(alert.channel || "in_app")}</span>
          </div>
          <p class="meta-row">${escapeHtml(alert.body || "")}</p>
          <div class="detail-row">
            <span>${escapeHtml(alert.alert_type || "alert")}</span>
            <span>${alert.created_at ? dateLabel(alert.created_at) : ""}</span>
          </div>
          <div class="detail-row">
            <span>${metadata.new_price_cad ? money(metadata.new_price_cad) : money(metadata.asking_price_cad)}</span>
            <span>${metadata.deal_score ? `Score ${score(metadata.deal_score)}` : ""}</span>
          </div>
          <div class="saved-search-actions">
            ${metadata.source_url ? `<a class="secondary button-link" href="${escapeAttr(metadata.source_url)}" target="_blank" rel="noreferrer">Open</a>` : ""}
            ${alert.status === "unread" ? `<button type="button" data-read-alert="${escapeHtml(alert.id)}">Read</button>` : ""}
          </div>
        </div>
      `;
    })
    .join("");

  alertsEl.querySelectorAll("[data-read-alert]").forEach((button) => {
    button.addEventListener("click", () => markAlertRead(button.dataset.readAlert));
  });
}

async function markAlertRead(alertId) {
  try {
    const response = await fetch(`/api/alerts/${encodeURIComponent(alertId)}/read`, { method: "PATCH" });
    const body = await parseJson(response);
    if (!response.ok) throw new Error(errorMessage(body, "Could not mark alert read"));
    state.alerts = state.alerts.map((alert) => (alert.id === body.id ? body : alert));
    renderAlerts();
  } catch (error) {
    showAlert(error.message);
  }
}

function alertChannelLabel(search) {
  if (!search.alerts_enabled) return "-";
  const channels = [];
  if (search.in_app_alerts_enabled) channels.push("in-app");
  if (search.email_alerts_enabled) channels.push("email");
  return escapeHtml(channels.join(" + ") || "none");
}

function selectSavedSearch(searchId) {
  const search = state.savedSearches.find((item) => item.id === searchId);
  if (!search) return;
  const filters = search.structured_filters || {};
  setValue("name", search.name || "");
  setValue("natural_language_query", search.natural_language_query || "");
  setValue("make", filters.make || "");
  setValue("model", filters.model || "");
  setValue("year_min", filters.year_min || "");
  setValue("year_max", filters.year_max || "");
  setValue("price_max_cad", filters.price_max_cad || "");
  setValue("mileage_max_km", filters.mileage_max_km || "");
  setValue("location_city", filters.location_city || search.location_city || "Montreal");
  setValue("location_province", filters.location_province || search.location_province || "QC");
  setValue("radius_km", filters.radius_km || search.radius_km || 50);
  setValue("listing_limit", search.listing_limit || 25);
  setValue("sources", search.sources || "both");
  setValue("max_candidates", search.max_candidates || 50);
  document.querySelector("#scheduled").checked = Boolean(search.scheduled);
  setValue("schedule_cron", search.schedule_cron || "daily");
  document.querySelector("#alerts_enabled").checked = Boolean(search.alerts_enabled);
  document.querySelector("#in_app_alerts_enabled").checked = search.in_app_alerts_enabled !== false;
  document.querySelector("#email_alerts_enabled").checked = Boolean(search.email_alerts_enabled);
  setValue("listing_url", search.listing_url || "");
  setValue("vin", search.vin || "");
  showOverpriced.checked = Boolean(search.include_overpriced);
  clearAlert();
}

function renderCandidates() {
  const includeOverpriced = showOverpriced.checked;
  const includeHidden = showHidden.checked;
  const candidates = state.candidates.filter((item) => {
    if (!includeOverpriced && item.is_overpriced) return false;
    if (!includeHidden && item.hidden) return false;
    return true;
  });
  document.querySelector("#result-heading").textContent = state.activeRunId
    ? `Run ${shortId(state.activeRunId)}`
    : "No run loaded";

  if (!candidates.length) {
    listEl.innerHTML = `<div class="opportunity-card"><div class="card-main"><h3>No candidates to show</h3><p class="meta-row">Run a search or enable filtered results.</p></div></div>`;
    updateSummary();
    return;
  }

  listEl.innerHTML = candidates
    .map((candidate, index) => {
      const active = candidate.id === state.activeCandidateId ? " active" : "";
      const rank = candidate.rank || index + 1;
      return `
        <button class="opportunity-card${active}" type="button" data-candidate-id="${escapeHtml(candidate.id || "")}">
          <div class="card-main">
            <div class="title-row">
              <h3>${escapeHtml(candidate.title || vehicleTitle(candidate))}</h3>
              ${pill(candidate.source || "source")}
            </div>
            <div class="meta-row">
              <span>#${rank}</span>
              <span>${money(candidate.asking_price_cad)}</span>
              <span>${number(candidate.mileage_km)} km</span>
              <span>${escapeHtml(locationLabel(candidate))}</span>
            </div>
            <div class="risk-row">
              ${recommendationPill(candidate.recommendation)}
              ${candidate.intake_mode === "single_listing" ? pill("single listing", "good") : ""}
              ${candidate.is_overpriced ? pill("overpriced", "warning") : pill("priced")}
              ${candidate.selected ? pill("selected", "good") : ""}
              ${candidate.hidden ? pill("hidden", "warning") : ""}
              ${candidate.image_risk_reasons?.length ? pill("image risk", "warning") : pill("images ok", "good")}
              ${candidate.missing_data?.length ? pill(`${candidate.missing_data.length} missing`, "danger") : pill("core data", "good")}
            </div>
          </div>
          <div class="score-stack">
            <span class="score">${score(candidate.deal_score)}</span>
            <span class="score-label">Deal score</span>
          </div>
        </button>
      `;
    })
    .join("");

  listEl.querySelectorAll("[data-candidate-id]").forEach((button) => {
    button.addEventListener("click", () => loadCandidate(button.dataset.candidateId));
  });
  updateSummary();
}

function renderSourceStatuses() {
  if (!state.sourceStatuses.length) {
    sourceStatusPanel.innerHTML = "";
    return;
  }

  sourceStatusPanel.innerHTML = state.sourceStatuses
    .map((status) => {
      const normalized = String(status.status || "skipped").toLowerCase();
      const detail = status.message || status.reason || `${status.listing_count || 0} parsed listings`;
      const diagnostics = status.diagnostics || {};
      return `
        <div class="source-status ${escapeHtml(normalized)}" title="${escapeAttr(detail)}">
          <span class="status-dot ${escapeHtml(normalized)}"></span>
          <strong>${escapeHtml(status.source_name || "source")}</strong>
          ${pill(normalized, statusTone(normalized))}
          <span>${escapeHtml(statusSummary(status))}</span>
          ${diagnosticPills(diagnostics)}
        </div>
      `;
    })
    .join("");
}

function renderHistory() {
  if (!state.runs.length) {
    historyEl.innerHTML = `<div class="run-card"><h3>No runs yet</h3><p class="meta-row">Run history appears after the first search.</p></div>`;
    return;
  }

  historyEl.innerHTML = state.runs
    .map((run) => {
      const active = run.id === state.activeRunId ? " active" : "";
      const filters = run.structured_filters || {};
      const title = run.name || "Search run";
      const subtitle = [
        filters.year_min,
        filters.make,
        filters.model,
        filters.location_city,
      ].filter(Boolean).join(" ");
      const sourceSummary = sourceStatusSummary(run.source_statuses || []);
      return `
        <button class="run-card${active}" type="button" data-run-id="${escapeHtml(run.id)}">
          <h3>${escapeHtml(title)}</h3>
          <div class="detail-row">
            <span>${escapeHtml(subtitle || run.natural_language_query || "Ad hoc search")}</span>
            <span>${run.candidate_count || 0} candidates</span>
          </div>
          <div class="detail-row">
            <span>${escapeHtml(dateLabel(run.created_at))}</span>
            <span>${escapeHtml(run.status || "unknown")}</span>
          </div>
          <div class="detail-row">
            <span>${escapeHtml(sourceSummary)}</span>
          </div>
        </button>
      `;
    })
    .join("");

  historyEl.querySelectorAll("[data-run-id]").forEach((button) => {
    button.addEventListener("click", () => loadRun(button.dataset.runId));
  });
}

function renderCandidateDetail(candidate) {
  detailTitle.textContent = candidate.title || vehicleTitle(candidate);
  if (candidate.source_url) {
    detailSourceLink.href = candidate.source_url;
    detailSourceLink.classList.remove("hidden");
  } else {
    detailSourceLink.classList.add("hidden");
  }

  const pricing = candidate.pricing_summary || {};
  const risk = candidate.risk_summary || {};
  detailEl.classList.remove("empty-state");
  detailEl.innerHTML = `
    <section class="detail-section">
      <h3>Workflow</h3>
      <div class="workflow-actions">
        <button id="toggle-selected" type="button" class="${candidate.selected ? "secondary" : ""}">
          ${candidate.selected ? "Unselect" : "Select"}
        </button>
        <button id="toggle-hidden" type="button" class="${candidate.hidden ? "" : "secondary"}">
          ${candidate.hidden ? "Unhide" : "Hide"}
        </button>
      </div>
      <button id="promote-candidate" type="button" class="${candidate.opportunity_id ? "secondary" : ""}">
        ${candidate.opportunity_id ? `Promoted ${shortId(candidate.opportunity_id)}` : "Promote to Opportunity"}
      </button>
      <div class="workflow-form">
        <label class="field">
          <span>Contact status</span>
          <select id="seller-contact-status">
            ${contactStatusOptions(candidate.seller_contact_status)}
          </select>
        </label>
        <label class="field">
          <span>Seller notes</span>
          <textarea id="seller-notes" maxlength="5000">${escapeHtml(candidate.seller_notes || "")}</textarea>
        </label>
        <button id="save-candidate-workflow" type="button">Save Candidate Notes</button>
      </div>
    </section>
    <section class="detail-section">
      <h3>Pricing</h3>
      <div class="data-grid">
        ${dataItem("Ask", money(candidate.asking_price_cad))}
        ${dataItem("Retail mid", money(candidate.estimated_retail_value_cad || pricing.retail_mid_cad))}
        ${dataItem("Max buy", money(candidate.max_buy_price_cad || pricing.max_buy_price_cad))}
        ${dataItem("Starting offer", money(pricing.starting_offer_cad))}
      </div>
    </section>
    <section class="detail-section">
      <h3>Vehicle</h3>
      <div class="data-grid">
        ${dataItem("VIN", candidate.vin || "Missing")}
        ${dataItem("Mileage", `${number(candidate.mileage_km)} km`)}
        ${dataItem("Body", candidate.body_style || "Unknown")}
        ${dataItem("Drivetrain", candidate.drivetrain || "Unknown")}
      </div>
    </section>
    <section class="detail-section">
      <h3>Risk</h3>
      ${tagList([
        ...(candidate.missing_data || []),
        ...(candidate.image_risk_reasons || []),
        ...(risk.risk_factors || []),
      ])}
    </section>
    <section class="detail-section">
      <h3>Relevance</h3>
      ${tagList(candidate.relevance_reasons || [])}
    </section>
    <section class="detail-section">
      <h3>Confidence</h3>
      ${confidenceGrid(candidate.confidence_by_section || {})}
    </section>
    <section class="detail-section">
      <h3>Images</h3>
      ${imageStrip(candidate.image_urls || [])}
    </section>
  `;

  document.querySelector("#toggle-selected").addEventListener("click", () => {
    updateCandidateWorkflow(candidate.id, { selected: !candidate.selected });
  });
  document.querySelector("#toggle-hidden").addEventListener("click", () => {
    updateCandidateWorkflow(candidate.id, { hidden: !candidate.hidden });
  });
  document.querySelector("#promote-candidate").addEventListener("click", () => {
    promoteCandidate(candidate.id);
  });
  document.querySelector("#save-candidate-workflow").addEventListener("click", () => {
    const status = document.querySelector("#seller-contact-status").value || null;
    const notes = document.querySelector("#seller-notes").value.trim() || null;
    updateCandidateWorkflow(candidate.id, {
      seller_contact_status: status,
      seller_notes: notes,
    });
  });
}

function renderEmptyDetail() {
  detailTitle.textContent = "Select a candidate";
  detailSourceLink.classList.add("hidden");
  detailEl.classList.add("empty-state");
  detailEl.innerHTML = "<p>Candidate pricing, risk, image, and confidence details will appear here.</p>";
}

function updateSummary(run) {
  const candidates = state.candidates || [];
  const scores = candidates.map((item) => Number(item.deal_score)).filter(Number.isFinite);
  const maxBuyValues = candidates.map((item) => Number(item.max_buy_price_cad)).filter(Number.isFinite);
  const sources = new Set((state.sourceStatuses || []).map((item) => item.source_name).filter(Boolean));
  document.querySelector("#metric-candidates").textContent = String(candidates.length);
  document.querySelector("#metric-score").textContent = scores.length
    ? String(Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length))
    : "-";
  document.querySelector("#metric-max-buy").textContent = maxBuyValues.length
    ? money(Math.max(...maxBuyValues))
    : "-";
  document.querySelector("#metric-sources").textContent = sources.size
    ? Array.from(sources).join(", ")
    : run?.status || "-";
}

function showSourceFailureAlert() {
  const failures = (state.sourceStatuses || []).filter((status) => status.status === "failed");
  if (!failures.length) return;
  showAlert(
    failures
      .map((status) => `${status.source_name}: ${status.message || status.reason || "source failed"}`)
      .join("; ")
  );
}

function dataItem(label, valueText) {
  return `<div class="data-item"><span>${escapeHtml(label)}</span><strong>${escapeHtml(valueText || "-")}</strong></div>`;
}

function tagList(items) {
  const filtered = [...new Set((items || []).filter(Boolean))];
  if (!filtered.length) return `<p class="meta-row">None reported.</p>`;
  return `<div class="tag-list">${filtered.map((item) => pill(String(item).replaceAll("_", " "))).join("")}</div>`;
}

function confidenceGrid(confidence) {
  const entries = Object.entries(confidence);
  if (!entries.length) return `<p class="meta-row">No confidence data.</p>`;
  return `<div class="data-grid">${entries.map(([key, valueText]) => dataItem(key.replaceAll("_", " "), String(valueText))).join("")}</div>`;
}

function imageStrip(urls) {
  if (!urls.length) return `<p class="meta-row">No listing images saved.</p>`;
  return `<div class="image-strip">${urls.slice(0, 6).map((url) => `<img src="${escapeAttr(url)}" alt="Listing image" loading="lazy" />`).join("")}</div>`;
}

function recommendationPill(valueText) {
  const value = String(valueText || "review").toLowerCase();
  if (value.includes("buy")) return pill(valueText, "good");
  if (value.includes("pass")) return pill(valueText, "danger");
  return pill(valueText || "review", "warning");
}

function statusTone(status) {
  if (status === "ok") return "good";
  if (status === "failed") return "danger";
  if (status === "empty") return "warning";
  return "";
}

function statusSummary(status) {
  if (status.status === "ok") return `${status.listing_count || 0} parsed`;
  if (status.status === "empty") return "no parsed listings";
  if (status.status === "failed") return status.reason || "failed";
  return status.status || "skipped";
}

function diagnosticPills(diagnostics) {
  const items = [
    diagnostics.app_mode,
    diagnostics.fixture_mode === true ? "fixture" : diagnostics.fixture_mode === false ? "live" : null,
    diagnostics.fetch_method,
    diagnostics.source_role,
    diagnostics.status_code ? `HTTP ${diagnostics.status_code}` : null,
    diagnostics.parser,
  ].filter(Boolean);
  if (!items.length) return "";
  return items.map((item) => pill(String(item).replaceAll("_", " "))).join("");
}

function contactStatusOptions(current) {
  const options = [
    ["", "Not contacted"],
    ["to_contact", "To contact"],
    ["contacted", "Contacted"],
    ["awaiting_reply", "Awaiting reply"],
    ["appointment_set", "Appointment set"],
    ["not_interested", "Not interested"],
  ];
  return options
    .map(([valueText, label]) => {
      const selected = (current || "") === valueText ? " selected" : "";
      return `<option value="${escapeAttr(valueText)}"${selected}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function checklistItems() {
  return [
    { key: "vin_confirmed", label: "VIN confirmed" },
    { key: "service_records_requested", label: "Service records requested" },
    { key: "lien_status_checked", label: "Lien checked" },
    { key: "history_report_checked", label: "History checked" },
    { key: "extra_photos_requested", label: "Extra photos" },
    { key: "visit_appointment_set", label: "Appointment set" },
  ];
}

function checklistHtml(opportunity) {
  const checklist = opportunity.visit_checklist || {};
  return checklistItems()
    .map((item) => {
      const checked = checklist[item.key] ? " checked" : "";
      return `
        <label class="checklist-item">
          <input type="checkbox" data-opportunity-checklist="${escapeAttr(opportunity.id)}" data-checklist-key="${escapeAttr(item.key)}"${checked} />
          <span>${escapeHtml(item.label)}</span>
        </label>
      `;
    })
    .join("");
}

function documentTypeOptions() {
  const options = [
    ["carfax_pdf", "CARFAX PDF"],
    ["uvip", "UVIP"],
    ["seller_document", "Seller document"],
    ["mechanic_quote", "Mechanic quote"],
    ["auction_condition_report", "Auction report"],
    ["service_invoice", "Service invoice"],
    ["ownership_document", "Ownership document"],
    ["ppsa_report", "PPSA report"],
    ["ppsr_report", "PPSR report"],
    ["lien_release", "Lien release"],
    ["lender_payout_statement", "Lender payout statement"],
    ["transport_canada_recall_report", "Transport Canada recall report"],
    ["oem_recall_report", "OEM recall report"],
    ["recall_completion_receipt", "Recall completion receipt"],
    ["import_compliance_document", "Import compliance document"],
    ["riv_inspection", "RIV inspection"],
    ["statement_of_compliance", "Statement of compliance"],
    ["cbb_valuation", "Canadian Black Book valuation"],
    ["manheim_mmr", "Manheim MMR"],
    ["openlane_auction_report", "OPENLANE auction report"],
    ["adesa_auction_report", "ADESA auction report"],
    ["traderev_bid_report", "TradeRev bid report"],
    ["trade_in_appraisal", "Trade-in appraisal"],
    ["wholesale_invoice", "Wholesale invoice"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function documentSummaryHtml(opportunity) {
  const documents = opportunity.documents?.documents || [];
  if (!documents.length) return `<p class="meta-row">No documents uploaded.</p>`;
  return `
    <div class="document-list">
      ${documents
        .slice(0, 4)
        .map((document) => `
          <a class="document-link" href="${escapeAttr(document.download_url)}" target="_blank" rel="noreferrer">
            <span>${escapeHtml(document.document_label || document.document_type || "Document")}</span>
            <strong>${escapeHtml(document.original_filename || "download")}</strong>
          </a>
        `)
        .join("")}
      ${documents.length > 4 ? `<p class="meta-row">${documents.length - 4} more uploaded</p>` : ""}
    </div>
  `;
}

function comparableSummaryHtml(opportunity) {
  const summary = state.comparableDetails[opportunity.id] || opportunity.comparables || {};
  const pricing = summary.pricing_summary || opportunity.candidate?.pricing_summary || {};
  return `
    <div class="comparable-summary">
      ${pill(`${summary.included_count ?? pricing.comparable_count ?? 0} included`, "good")}
      ${summary.excluded_count ? pill(`${summary.excluded_count} excluded`, "warning") : ""}
      <p class="meta-row">Retail mid ${money(pricing.retail_mid_cad)} / Max buy ${money(pricing.max_buy_price_cad)}</p>
    </div>
  `;
}

function comparableEditorHtml(opportunity) {
  const detail = state.comparableDetails[opportunity.id];
  if (!detail?.comparables?.length) return "";
  return `
    <div class="comparable-list">
      ${detail.comparables
        .slice(0, 8)
        .map((comparable) => comparableRowHtml(comparable, opportunity.id))
        .join("")}
      ${detail.comparables.length > 8 ? `<p class="meta-row">${detail.comparables.length - 8} more comparables hidden</p>` : ""}
    </div>
  `;
}

function comparableRowHtml(comparable, opportunityId) {
  const title = [comparable.year, comparable.make, comparable.model, comparable.trim].filter(Boolean).join(" ") || "Comparable";
  const meta = [
    comparable.source_name,
    comparable.mileage_km ? `${number(comparable.mileage_km)} km` : null,
    comparable.similarity_score != null ? `sim ${comparable.similarity_score}` : null,
  ].filter(Boolean).join(" / ");
  if (!comparable.included) {
    return `
      <div class="comparable-row excluded">
        <div>
          <strong>${escapeHtml(title)}</strong>
          <p class="meta-row">${escapeHtml(meta)} / ${money(comparable.asking_price_cad)}</p>
          <p class="meta-row">Excluded: ${escapeHtml(comparable.excluded_reason || "dealer removed")}</p>
        </div>
      </div>
    `;
  }
  return `
    <div class="comparable-row">
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p class="meta-row">${escapeHtml(meta)} / ${money(comparable.asking_price_cad)}</p>
      </div>
      <label class="field">
        <span>Reason</span>
        <input data-comparable-reason="${escapeAttr(comparable.id)}" autocomplete="off" />
      </label>
      <button type="button" class="secondary" data-remove-comparable="${escapeAttr(comparable.id)}" data-comparable-opportunity="${escapeAttr(opportunityId)}">Remove</button>
    </div>
  `;
}

function dealerCorrectionSummaryHtml(opportunity) {
  const corrections = opportunity.dealer_corrections?.latest || [];
  if (!corrections.length) return `<p class="meta-row">No dealer corrections saved.</p>`;
  return `
    <div class="dealer-correction-list">
      ${corrections
        .slice(0, 4)
        .map((correction) => {
          const field = `${correction.entity_type || ""}.${correction.field_name || ""}`.replace(/^\./, "");
          const value = correction.new_value == null ? "-" : String(correction.new_value).replaceAll("_", " ");
          return `
            <div class="correction-pill">
              <span>${escapeHtml(field)}</span>
              <strong>${escapeHtml(value)}</strong>
            </div>
          `;
        })
        .join("")}
      ${corrections.length > 4 ? `<p class="meta-row">${corrections.length - 4} more active corrections</p>` : ""}
    </div>
  `;
}

function dealerCorrectionFormHtml(opportunity) {
  const candidate = opportunity.candidate || {};
  return `
    <div class="dealer-correction-grid">
      <label class="field">
        <span>Trim</span>
        <input data-correction-trim="${escapeAttr(opportunity.id)}" placeholder="${escapeAttr(candidate.trim || "Correct trim")}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Mileage km</span>
        <input data-correction-mileage="${escapeAttr(opportunity.id)}" inputmode="numeric" placeholder="${escapeAttr(candidate.mileage_km || "Correct mileage")}" />
      </label>
      <label class="field">
        <span>Accident history</span>
        <select data-correction-accident-status="${escapeAttr(opportunity.id)}">
          ${accidentCorrectionOptions()}
        </select>
      </label>
      <label class="field">
        <span>Lien status</span>
        <select data-correction-lien-status="${escapeAttr(opportunity.id)}">
          ${lienCorrectionOptions()}
        </select>
      </label>
      <label class="field field-wide">
        <span>Reason</span>
        <textarea data-correction-reason="${escapeAttr(opportunity.id)}" maxlength="1000"></textarea>
      </label>
    </div>
  `;
}

function titleEvidenceSummaryHtml(opportunity) {
  const latest = opportunity.title_evidence?.latest;
  if (!latest) return `<p class="meta-row">No title evidence saved.</p>`;
  const summary = [
    latest.provider || latest.source_type,
    latest.lookup_reference,
    latest.lienholder_name ? `Lienholder: ${latest.lienholder_name}` : null,
    latest.payout_required ? `Payout ${latest.payout_status || "unknown"}` : null,
  ].filter(Boolean);
  return `
    <div class="title-evidence-summary">
      ${pill(String(latest.title_clearance_status || "unknown").replaceAll("_", " "), titleStatusTone(latest.title_clearance_status))}
      <p class="meta-row">${escapeHtml(summary.join(" / ") || "Latest evidence saved")}</p>
    </div>
  `;
}

function recallComplianceSummaryHtml(opportunity) {
  const latest = opportunity.recall_compliance?.latest;
  if (!latest) return `<p class="meta-row">No recall or import compliance evidence saved.</p>`;
  const summary = [
    latest.provider || latest.source_type,
    latest.lookup_reference,
    latest.campaign_number ? `Campaign: ${latest.campaign_number}` : null,
    latest.remedy_status ? `Remedy ${latest.remedy_status}` : null,
    latest.riv_case_number ? `RIV ${latest.riv_case_number}` : null,
  ].filter(Boolean);
  return `
    <div class="recall-compliance-summary">
      ${pill(String(opportunity.recall_compliance?.status || latest.recall_status || "unknown").replaceAll("_", " "), recallStatusTone(opportunity.recall_compliance?.status || latest.recall_status))}
      <p class="meta-row">${escapeHtml(summary.join(" / ") || "Latest evidence saved")}</p>
    </div>
  `;
}

function titleEvidenceFormHtml(opportunity) {
  return `
    <div class="title-evidence-grid">
      <label class="field">
        <span>Source</span>
        <select data-title-source="${escapeAttr(opportunity.id)}">
          ${titleSourceOptions()}
        </select>
      </label>
      <label class="field">
        <span>Status</span>
        <select data-title-status="${escapeAttr(opportunity.id)}">
          ${titleStatusOptions()}
        </select>
      </label>
      <label class="field">
        <span>Provider</span>
        <input data-title-provider="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Reference</span>
        <input data-title-reference="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Linked document</span>
        <select data-title-document="${escapeAttr(opportunity.id)}">
          ${titleDocumentOptions(opportunity)}
        </select>
      </label>
      <label class="field">
        <span>Seller</span>
        <input data-title-seller="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Registered owner</span>
        <input data-title-owner="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="checklist-item">
        <input type="checkbox" data-title-ownership-verified="${escapeAttr(opportunity.id)}" />
        <span>Ownership verified</span>
      </label>
      <label class="checklist-item">
        <input type="checkbox" data-title-payout-required="${escapeAttr(opportunity.id)}" />
        <span>Payout required</span>
      </label>
      <label class="field">
        <span>Lienholder</span>
        <input data-title-lienholder="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Lien amount</span>
        <input data-title-lien-amount="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Payout amount</span>
        <input data-title-payout-amount="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Payout due</span>
        <input data-title-payout-due="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Payout status</span>
        <select data-title-payout-status="${escapeAttr(opportunity.id)}">
          ${payoutStatusOptions()}
        </select>
      </label>
      <label class="field field-wide">
        <span>Notes</span>
        <textarea data-title-notes="${escapeAttr(opportunity.id)}" maxlength="5000"></textarea>
      </label>
    </div>
  `;
}

function recallComplianceFormHtml(opportunity) {
  return `
    <div class="recall-compliance-grid">
      <label class="field">
        <span>Source</span>
        <select data-recall-source="${escapeAttr(opportunity.id)}">
          ${recallSourceOptions()}
        </select>
      </label>
      <label class="field">
        <span>Recall status</span>
        <select data-recall-status="${escapeAttr(opportunity.id)}">
          ${recallStatusOptions()}
        </select>
      </label>
      <label class="field">
        <span>Compliance</span>
        <select data-compliance-status="${escapeAttr(opportunity.id)}">
          ${complianceStatusOptions()}
        </select>
      </label>
      <label class="field">
        <span>Provider</span>
        <input data-recall-provider="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Reference</span>
        <input data-recall-reference="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Linked document</span>
        <select data-recall-document="${escapeAttr(opportunity.id)}">
          ${titleDocumentOptions(opportunity)}
        </select>
      </label>
      <label class="field">
        <span>Campaign</span>
        <input data-recall-campaign="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Remedy</span>
        <select data-recall-remedy="${escapeAttr(opportunity.id)}">
          ${remedyStatusOptions()}
        </select>
      </label>
      <label class="field">
        <span>Completed</span>
        <input data-recall-completion-date="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Campaign description</span>
        <textarea data-recall-description="${escapeAttr(opportunity.id)}" maxlength="1000"></textarea>
      </label>
      <label class="field">
        <span>Import country</span>
        <input data-import-country="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Import form</span>
        <input data-import-form="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>RIV case</span>
        <input data-riv-case="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="checklist-item">
        <input type="checkbox" data-inspection-required="${escapeAttr(opportunity.id)}" />
        <span>Inspection required</span>
      </label>
      <label class="field">
        <span>Inspection due</span>
        <input data-inspection-deadline="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Notes</span>
        <textarea data-recall-notes="${escapeAttr(opportunity.id)}" maxlength="5000"></textarea>
      </label>
    </div>
  `;
}

function wholesaleEvidenceSummaryHtml(opportunity) {
  const latest = opportunity.wholesale_evidence?.latest;
  const support = opportunity.wholesale_evidence?.support || {};
  if (!latest) return `<p class="meta-row">No wholesale or trade-in evidence saved.</p>`;
  const summary = [
    latest.provider || latest.source_type,
    latest.lookup_reference,
    support.supported_max_buy_cad ? `Support ${money(support.supported_max_buy_cad)}` : null,
    latest.bid_count != null ? `${latest.bid_count} bids` : null,
    latest.condition_grade ? `Condition ${String(latest.condition_grade).replaceAll("_", " ")}` : null,
  ].filter(Boolean);
  return `
    <div class="wholesale-evidence-summary">
      ${pill(String(opportunity.wholesale_evidence?.status || "unknown").replaceAll("_", " "), wholesaleStatusTone(opportunity.wholesale_evidence?.status))}
      <p class="meta-row">${escapeHtml(summary.join(" / ") || "Latest evidence saved")}</p>
    </div>
  `;
}

function wholesaleEvidenceFormHtml(opportunity) {
  return `
    <div class="wholesale-evidence-grid">
      <label class="field">
        <span>Source</span>
        <select data-wholesale-source="${escapeAttr(opportunity.id)}">
          ${wholesaleSourceOptions()}
        </select>
      </label>
      <label class="field">
        <span>Provider</span>
        <input data-wholesale-provider="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Reference</span>
        <input data-wholesale-reference="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field">
        <span>Region</span>
        <input data-wholesale-region="${escapeAttr(opportunity.id)}" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Linked document</span>
        <select data-wholesale-document="${escapeAttr(opportunity.id)}">
          ${titleDocumentOptions(opportunity)}
        </select>
      </label>
      <label class="field">
        <span>Wholesale low</span>
        <input data-wholesale-low="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Wholesale avg</span>
        <input data-wholesale-avg="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Wholesale high</span>
        <input data-wholesale-high="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Trade-in</span>
        <input data-trade-in-value="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Retail guide</span>
        <input data-wholesale-retail="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Auction low</span>
        <input data-auction-sale-low="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Auction avg</span>
        <input data-auction-sale-avg="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Auction high</span>
        <input data-auction-sale-high="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Bid count</span>
        <input data-bid-count="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Bidders</span>
        <input data-bidder-count="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>High bid</span>
        <input data-high-bid="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Sale price</span>
        <input data-sale-price="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Reserve</span>
        <input data-reserve-price="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Condition</span>
        <select data-condition-grade="${escapeAttr(opportunity.id)}">
          ${conditionGradeOptions()}
        </select>
      </label>
      <label class="field">
        <span>Condition score</span>
        <input data-condition-score="${escapeAttr(opportunity.id)}" inputmode="decimal" />
      </label>
      <label class="field">
        <span>Buyer fee</span>
        <input data-buyer-fee="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Transport</span>
        <input data-wholesale-transport="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field">
        <span>Recon</span>
        <input data-wholesale-recon="${escapeAttr(opportunity.id)}" inputmode="numeric" />
      </label>
      <label class="field field-wide">
        <span>Condition notes</span>
        <textarea data-condition-notes="${escapeAttr(opportunity.id)}" maxlength="2000"></textarea>
      </label>
      <label class="field field-wide">
        <span>Notes</span>
        <textarea data-wholesale-notes="${escapeAttr(opportunity.id)}" maxlength="5000"></textarea>
      </label>
    </div>
  `;
}

function titleSourceOptions() {
  const options = [
    ["manual", "Manual"],
    ["uvip", "UVIP"],
    ["ppsa_lookup", "PPSA lookup"],
    ["ppsr_lookup", "PPSR lookup"],
    ["seller_ownership", "Seller ownership"],
    ["lender_payout", "Lender payout"],
    ["lien_release", "Lien release"],
    ["document_upload", "Document upload"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function recallSourceOptions() {
  const options = [
    ["manual", "Manual"],
    ["transport_canada", "Transport Canada"],
    ["oem_portal", "OEM portal"],
    ["dealer_service", "Dealer service"],
    ["import_compliance", "Import compliance"],
    ["riv", "RIV"],
    ["document_upload", "Document upload"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function wholesaleSourceOptions() {
  const options = [
    ["manual", "Manual"],
    ["canadian_black_book", "Canadian Black Book"],
    ["manheim_mmr", "Manheim MMR"],
    ["openlane", "OPENLANE"],
    ["adesa", "ADESA"],
    ["traderev", "TradeRev"],
    ["auction_report", "Auction report"],
    ["trade_in_appraisal", "Trade-in appraisal"],
    ["document_upload", "Document upload"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function titleStatusOptions() {
  const options = [
    ["unknown", "Unknown"],
    ["needs_review", "Needs review"],
    ["clear", "Clear"],
    ["lien_found", "Lien found"],
    ["payout_pending", "Payout pending"],
    ["payout_ready", "Payout ready"],
    ["payout_paid", "Payout paid"],
    ["released", "Released"],
    ["blocked", "Blocked"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function accidentCorrectionOptions() {
  const options = [
    ["", "No change"],
    ["none_reported", "None reported"],
    ["accident_reported", "Accident reported"],
    ["minor_damage", "Minor damage"],
    ["moderate_damage", "Moderate damage"],
    ["major_damage", "Major damage"],
    ["unknown", "Unknown"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function lienCorrectionOptions() {
  const options = [
    ["", "No change"],
    ["clear", "Clear"],
    ["released", "Released"],
    ["lien_found", "Lien found"],
    ["payout_pending", "Payout pending"],
    ["payout_ready", "Payout ready"],
    ["payout_paid", "Payout paid"],
    ["needs_review", "Needs review"],
    ["blocked", "Blocked"],
    ["unknown", "Unknown"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function recallStatusOptions() {
  const options = [
    ["unknown", "Unknown"],
    ["not_checked", "Not checked"],
    ["no_open_recalls", "No open recalls"],
    ["open_recall", "Open recall"],
    ["incomplete", "Incomplete"],
    ["completed", "Completed"],
    ["needs_review", "Needs review"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function complianceStatusOptions() {
  const options = [
    ["unknown", "Unknown"],
    ["not_applicable", "Not applicable"],
    ["needs_review", "Needs review"],
    ["compliant", "Compliant"],
    ["non_compliant", "Non-compliant"],
    ["needs_inspection", "Needs inspection"],
    ["import_pending", "Import pending"],
    ["blocked", "Blocked"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function payoutStatusOptions() {
  const options = [
    ["unknown", "Unknown"],
    ["not_required", "Not required"],
    ["requested", "Requested"],
    ["received", "Received"],
    ["paid", "Paid"],
    ["released", "Released"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function remedyStatusOptions() {
  const options = [
    ["unknown", "Unknown"],
    ["not_required", "Not required"],
    ["required", "Required"],
    ["scheduled", "Scheduled"],
    ["completed", "Completed"],
    ["parts_unavailable", "Parts unavailable"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function conditionGradeOptions() {
  const options = [
    ["unknown", "Unknown"],
    ["rough", "Rough"],
    ["average", "Average"],
    ["clean", "Clean"],
    ["extra_clean", "Extra clean"],
    ["auction_1", "Auction 1"],
    ["auction_2", "Auction 2"],
    ["auction_3", "Auction 3"],
    ["auction_4", "Auction 4"],
    ["auction_5", "Auction 5"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function titleDocumentOptions(opportunity) {
  const documents = opportunity.documents?.documents || [];
  return [
    `<option value="">No linked document</option>`,
    ...documents.map((document) => {
      const label = `${document.document_label || document.document_type}: ${document.original_filename || document.id}`;
      return `<option value="${escapeAttr(document.id)}">${escapeHtml(label)}</option>`;
    }),
  ].join("");
}

function titleStatusTone(status) {
  if (["clear", "released"].includes(status)) return "good";
  if (["lien_found", "blocked"].includes(status)) return "danger";
  if (["payout_pending", "payout_ready", "payout_paid", "needs_review"].includes(status)) return "warning";
  return "";
}

function recallStatusTone(status) {
  if (["clear", "no_open_recalls", "completed", "compliant", "not_applicable"].includes(status)) return "good";
  if (["open_recall", "incomplete", "non_compliant", "blocked"].includes(status)) return "danger";
  if (["needs_review", "needs_inspection", "import_pending", "not_checked", "unknown"].includes(status)) return "warning";
  return "";
}

function wholesaleStatusTone(status) {
  if (status === "supported") return "good";
  if (status === "support_below_retail_max") return "warning";
  if (status === "needs_values") return "warning";
  return "";
}

function feedbackFormHtml(opportunity) {
  return `
    <div class="feedback-grid">
      <label class="field">
        <span>Useful</span>
        <select data-feedback-usefulness="${escapeAttr(opportunity.id)}">
          ${ratingOptions(4)}
        </select>
      </label>
      <label class="field">
        <span>Accurate</span>
        <select data-feedback-accuracy="${escapeAttr(opportunity.id)}">
          ${ratingOptions(4)}
        </select>
      </label>
      <label class="field field-wide">
        <span>Decision</span>
        <select data-feedback-decision="${escapeAttr(opportunity.id)}">
          ${decisionOptions()}
        </select>
      </label>
      <label class="field field-wide">
        <span>Missing info</span>
        <input data-feedback-missing="${escapeAttr(opportunity.id)}" placeholder="VIN, lien, service records" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Incorrect info</span>
        <input data-feedback-incorrect="${escapeAttr(opportunity.id)}" placeholder="price, mileage, trim" autocomplete="off" />
      </label>
      <label class="field field-wide">
        <span>Notes</span>
        <textarea data-feedback-notes="${escapeAttr(opportunity.id)}" maxlength="5000"></textarea>
      </label>
    </div>
  `;
}

function ratingOptions(current) {
  return [1, 2, 3, 4, 5]
    .map((valueText) => `<option value="${valueText}"${valueText === current ? " selected" : ""}>${valueText}</option>`)
    .join("");
}

function decisionOptions() {
  const options = [
    ["undecided", "Undecided"],
    ["pursue", "Pursue"],
    ["pass", "Pass"],
    ["contacted", "Contacted"],
    ["visited", "Visited"],
    ["offered", "Offered"],
    ["bought", "Bought"],
  ];
  return options.map(([valueText, label]) => `<option value="${escapeAttr(valueText)}">${escapeHtml(label)}</option>`).join("");
}

function stageOptions(current) {
  const options = [
    ["new", "New"],
    ["candidate", "Candidate"],
    ["needs_data", "Needs Data"],
    ["contact_seller", "Contact Seller"],
    ["ready_to_visit", "Ready to Visit"],
    ["visited", "Visited"],
    ["offer_made", "Offer Made"],
    ["bought", "Bought"],
    ["passed", "Passed"],
  ];
  return options
    .map(([valueText, label]) => {
      const selected = (current || "new") === valueText ? " selected" : "";
      return `<option value="${escapeAttr(valueText)}"${selected}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function stageLabel(valueText) {
  return String(valueText || "new")
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function readinessWarningHtml(opportunity) {
  const warnings = opportunity.readiness_warnings || [];
  if (!warnings.length) return "";
  const fields = warnings.flatMap((warning) => warning.fields || []).filter(Boolean);
  return `
    <div class="readiness-warning">
      <strong>Missing before visit</strong>
      ${tagList(fields)}
    </div>
  `;
}

function upsertOpportunity(opportunity) {
  state.opportunities = state.opportunities.map((item) =>
    item.id === opportunity.id ? opportunity : item
  );
  if (!state.opportunities.some((item) => item.id === opportunity.id)) {
    state.opportunities = [opportunity, ...state.opportunities];
  }
}

function setLatestReportOnOpportunity(opportunityId, report) {
  state.opportunities = state.opportunities.map((item) =>
    item.id === opportunityId
      ? {
          ...item,
          latest_report: {
            id: report.id,
            version: report.version,
            status: report.status,
            recommendation: report.recommendation,
            html_url: report.html_url,
            created_at: report.created_at,
          },
        }
      : item
  );
}

function valueFromData(name, opportunityId) {
  const input = opportunitiesEl.querySelector(`[data-${name}="${cssEscape(opportunityId)}"]`);
  return input?.value.trim() || "";
}

function numberFromData(name, opportunityId) {
  const valueText = valueFromData(name, opportunityId);
  if (valueText === "") return null;
  const parsed = Number(valueText);
  return Number.isFinite(parsed) ? parsed : null;
}

function integerFromData(name, opportunityId) {
  const value = numberFromData(name, opportunityId);
  return Number.isInteger(value) ? value : null;
}

function checkboxFromData(name, opportunityId) {
  const input = opportunitiesEl.querySelector(`[data-${name}="${cssEscape(opportunityId)}"]`);
  return Boolean(input?.checked);
}

function listFromData(name, opportunityId) {
  return valueFromData(name, opportunityId)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function sourceStatusSummary(statuses) {
  if (!statuses.length) return "No source status";
  return statuses
    .map((status) => `${status.source_name}: ${status.status}`)
    .join(", ");
}

function filterLabel(key) {
  const labels = {
    make: "Make",
    model: "Model",
    year_min: "Year min",
    year_max: "Year max",
    price_min_cad: "Min price",
    price_max_cad: "Max price",
    mileage_max_km: "Max km",
    location_city: "City",
    location_province: "Province",
    radius_km: "Radius",
    seller_type: "Seller",
  };
  return labels[key] || key;
}

function filterValue(key, valueText) {
  if (key.includes("price")) return money(valueText);
  if (key === "mileage_max_km") return `${number(valueText)} km`;
  if (key === "radius_km") return `${number(valueText)} km`;
  return String(valueText);
}

function pill(valueText, tone = "") {
  return `<span class="pill ${tone}">${escapeHtml(String(valueText || "-"))}</span>`;
}

function setLoading(isLoading) {
  state.loading = isLoading;
  runButton.disabled = isLoading;
  interpretButton.disabled = isLoading;
  analyzePromoteButton.disabled = isLoading;
  saveButton.disabled = isLoading;
  saveSettingsButton.disabled = isLoading;
  refreshHistory.disabled = isLoading;
  refreshSavedSearches.disabled = isLoading;
  refreshOpportunities.disabled = isLoading;
  refreshAlerts.disabled = isLoading;
  runButton.textContent = isLoading ? "Running" : "Run Search";
}

function showAlert(message) {
  alertRegion.innerHTML = `<div class="alert">${escapeHtml(message)}</div>`;
}

function clearAlert() {
  alertRegion.innerHTML = "";
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function errorMessage(body, fallback) {
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  return fallback;
}

function value(id) {
  return document.querySelector(`#${id}`).value.trim();
}

function setValue(id, nextValue) {
  const input = document.querySelector(`#${id}`);
  if (input) input.value = nextValue ?? "";
}

function numberValue(id) {
  const raw = value(id);
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function csvTerms(raw) {
  const seen = new Set();
  return String(raw || "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function money(valueText) {
  const value = Number(valueText);
  if (!Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0,
  }).format(value);
}

function number(valueText) {
  const value = Number(valueText);
  if (!Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 0 }).format(value);
}

function score(valueText) {
  const value = Number(valueText);
  return Number.isFinite(value) ? String(Math.round(value)) : "-";
}

function locationLabel(candidate) {
  return [candidate.location_city, candidate.location_province].filter(Boolean).join(", ");
}

function vehicleTitle(candidate) {
  return [candidate.year, candidate.make, candidate.model, candidate.trim].filter(Boolean).join(" ") || "Untitled listing";
}

function shortId(id) {
  return String(id || "").slice(0, 8);
}

function dateLabel(valueText) {
  if (!valueText) return "No date";
  const date = new Date(valueText);
  if (Number.isNaN(date.getTime())) return valueText;
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function escapeHtml(valueText) {
  return String(valueText)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(valueText) {
  return escapeHtml(valueText).replaceAll("`", "&#096;");
}

function cssEscape(valueText) {
  if (window.CSS?.escape) return window.CSS.escape(valueText);
  return String(valueText).replaceAll('"', '\\"');
}
