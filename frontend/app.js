const $ = (selector) => document.querySelector(selector);

const state = {
  filters: { country: [], institution: [], category: [] },
};

function splitList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function setStatus(element, message, ok = true) {
  element.textContent = message;
  element.classList.toggle("ok", ok);
  element.classList.toggle("error", !ok);
  if (message) toast(message, ok ? "ok" : "error");
}

// Escapa texto para insertarlo de forma segura en innerHTML
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Toast notifications (slide-in arriba a la derecha, auto-dismiss)
function toast(message, type = "ok") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  // Forzar reflow para la animación de entrada
  requestAnimationFrame(() => el.classList.add("toast-show"));
  setTimeout(() => {
    el.classList.remove("toast-show");
    setTimeout(() => el.remove(), 300);
  }, type === "error" ? 6000 : 3500);
}

// Deshabilita un botón y muestra estado de carga mientras corre fn()
async function withBusy(button, busyLabel, fn) {
  if (!button) return fn();
  const original = button.innerHTML;
  button.disabled = true;
  button.classList.add("is-busy");
  button.innerHTML = `<span class="btn-spinner"></span>${busyLabel}`;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.classList.remove("is-busy");
    button.innerHTML = original;
  }
}

// Banner de error de conexión global
function setConnectionError(visible) {
  const banner = document.getElementById("connection-banner");
  if (!banner) return;
  banner.hidden = !visible;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = "Ocurrió un error";
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function activeCompanyId() {
  return localStorage.getItem("company_id") || null;
}

function companyQuery() {
  const id = activeCompanyId();
  return id ? `company_id=${id}` : "";
}

function withCompany(params = {}) {
  const id = activeCompanyId();
  if (id) params.company_id = id;
  return params;
}

function fillSelect(select, values, placeholder) {
  const current = select.value;
  select.innerHTML = `<option value="">${placeholder}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = values.includes(current) ? current : "";
}

async function loadCompanies() {
  const data = await api("/companies");
  const select = $("#companySelect");
  const current = String(activeCompanyId() || "");
  // Clear and re-populate
  while (select.firstChild) select.removeChild(select.firstChild);
  data.items.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = String(c.id);
    opt.textContent = c.company_name;
    select.appendChild(opt);
  });
  // Activate the right option
  const match = data.items.find((c) => String(c.id) === current);
  if (match) {
    select.value = String(match.id);
  } else if (data.items.length) {
    const firstId = String(data.items[0].id);
    localStorage.setItem("company_id", firstId);
    select.value = firstId;
  }
}

async function loadFilters() {
  state.filters = await api("/filters");
  fillSelect($("#filterCountry"), state.filters.country, "Todos");
  fillSelect($("#filterInstitution"), state.filters.institution, "Todas");
  fillSelect($("#filterCategory"), state.filters.category, "Todas");
  fillSelect($("#dashCountry"), state.filters.country, "Todos");
  fillSelect($("#dashInstitution"), state.filters.institution, "Todas");
}

// Industry chips helpers (used both in dashboard profile form and onboarding)
function getCheckedIndustries(containerId) {
  return [...document.querySelectorAll(`#${containerId} input[type="checkbox"]:checked`)].map((c) => c.value);
}

function setCheckedIndustries(containerId, values) {
  document.querySelectorAll(`#${containerId} input[type="checkbox"]`).forEach((cb) => {
    cb.checked = values.includes(cb.value);
  });
  // Custom chips: add any value not in predefined checkboxes
  const predefined = [...document.querySelectorAll(`#${containerId} input[type="checkbox"]`)].map((c) => c.value);
  values.filter((v) => !predefined.includes(v)).forEach((v) => addCustomIndustryChip(containerId, v));
}

function addCustomIndustryChip(containerId, value) {
  const trimmed = value.trim();
  if (!trimmed) return;
  const container = $(`#${containerId}`);
  // Avoid duplicates (sin selector dinámico para no romper con comillas)
  const match = [...container.querySelectorAll("input[type=checkbox]")].find((c) => c.value === trimmed);
  if (match) {
    match.checked = true;
    return;
  }
  const label = document.createElement("label");
  label.className = "chip-check";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.value = trimmed;
  checkbox.checked = true;
  label.appendChild(checkbox);
  label.appendChild(document.createTextNode(" " + trimmed));
  // Insert before the custom-row div
  const customRow = container.querySelector(".chip-custom-row");
  container.insertBefore(label, customRow);
}

async function loadProfile() {
  const cid = activeCompanyId();
  const qs = cid ? `?company_id=${cid}` : "";
  const profile = await api(`/company-profile${qs}`);
  if (!profile.id) return;

  const form = $("#profileForm");
  form.company_name.value = profile.company_name || "";
  setCheckedIndustries("industryChips", profile.industry || []);
  form.countries.value = (profile.countries || []).join(", ");
  form.product_categories.value = (profile.product_categories || []).join(", ");
  form.keywords.value = (profile.keywords || []).join(", ");
  form.excluded_topics.value = (profile.excluded_topics || []).join(", ");
  form.internal_areas.value = (profile.internal_areas || []).join(", ");
  form.company_description.value = profile.company_description || "";
  form.notes.value = profile.notes || "";

  // Store the profile id for updates
  form.dataset.profileId = profile.id;
}

function activeAlertFilters() {
  return {
    country: $("#filterCountry").value,
    institution: $("#filterInstitution").value,
    category: $("#filterCategory").value,
    date_from: $("#filterDateFrom").value,
    date_to: $("#filterDateTo").value,
  };
}

function toQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  });
  return query.toString();
}

async function loadSummary() {
  const summary = await api(`/dashboard-summary?${companyQuery()}`);
  const cards = [
    ["total_alerts", "Total de alertas"],
    ["evaluated_alerts", "Alertas evaluadas"],
    ["relevant_alerts", "Alertas relevantes"],
    ["priority_high", "Prioridad alta"],
    ["priority_medium", "Prioridad media"],
    ["priority_low", "Prioridad baja"],
    ["requires_human_review", "Revisión humana"],
  ];

  $("#metrics").innerHTML = cards
    .map(([key, label]) => `
      <article class="metric-card">
        <span class="metric-value">${summary[key] || 0}</span>
        <span class="metric-label">${label}</span>
      </article>
    `)
    .join("");

  renderPriorityChart(summary);
}

// Gráfico de distribución de prioridades en SVG puro (sin librerías)
function renderPriorityChart(summary) {
  const host = $("#priorityChart");
  if (!host) return;
  const segments = [
    { key: "priority_high", label: "Alta", color: "var(--danger)" },
    { key: "priority_medium", label: "Media", color: "var(--warn)" },
    { key: "priority_low", label: "Baja", color: "var(--ok)" },
  ];
  const values = segments.map((s) => Number(summary[s.key] || 0));
  const total = values.reduce((a, b) => a + b, 0);

  if (!total) {
    host.innerHTML = `<p class="chart-empty">Sin alertas relevantes evaluadas todavía.</p>`;
    return;
  }

  // Donut: construir arcos proporcionales
  const radius = 52, cx = 60, cy = 60, circ = 2 * Math.PI * radius;
  let offset = 0;
  const arcs = segments
    .map((s, i) => {
      const frac = values[i] / total;
      const dash = `${frac * circ} ${circ}`;
      const arc = `<circle cx="${cx}" cy="${cy}" r="${radius}" fill="none"
        stroke="${s.color}" stroke-width="16"
        stroke-dasharray="${dash}" stroke-dashoffset="${-offset * circ}"
        transform="rotate(-90 ${cx} ${cy})"></circle>`;
      offset += frac;
      return arc;
    })
    .join("");

  const legend = segments
    .map((s, i) => `
      <li><span class="legend-dot" style="background:${s.color}"></span>
      ${s.label} <strong>${values[i]}</strong></li>`)
    .join("");

  host.innerHTML = `
    <svg viewBox="0 0 120 120" class="donut" role="img" aria-label="Distribución de prioridades">
      <circle cx="${cx}" cy="${cy}" r="${radius}" fill="none" stroke="var(--line)" stroke-width="16"></circle>
      ${arcs}
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" class="donut-total">${total}</text>
      <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="donut-sub">relevantes</text>
    </svg>
    <ul class="chart-legend">${legend}</ul>`;
}

function priorityBadge(priority) {
  const value = priority || "no_relevante";
  return `<span class="priority ${value}">${escapeHtml(value.replace("_", " "))}</span>`;
}

function confidenceBadge(confidence) {
  const value = confidence || "baja";
  return `<span class="confidence ${value}" title="Confianza del agente">${escapeHtml(value)}</span>`;
}

function emptyRow(message, cta) {
  return `
    <tr class="empty-row"><td colspan="6">
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <p class="empty-title">${escapeHtml(message)}</p>
        ${cta ? `<p class="empty-cta">${cta}</p>` : ""}
      </div>
    </td></tr>`;
}

async function loadAssessments() {
  const params = withCompany({
    priority: $("#dashPriority").value,
    country: $("#dashCountry").value,
    institution: $("#dashInstitution").value,
    requires_human_review: $("#dashReview").value,
  });
  const data = await api(`/assessments?${toQuery(params)}`);
  const rows = $("#assessmentRows");

  if (!data.items.length) {
    rows.innerHTML = emptyRow(
      "Todavía no hay evaluaciones para mostrar.",
      'Cargá un CSV o ejecutá el agente desde <strong>Configuración</strong>.'
    );
    return;
  }

  rows.innerHTML = data.items
    .map((item) => {
      const review = item.requires_human_review
        ? `<span class="review-flag" title="Requiere revisión humana">⚠ Revisión</span>`
        : "";
      const areas = (item.impacted_areas || []).map(escapeHtml).join(", ");
      // El detalle (siempre presente) recoge todo lo que ya no va en columnas.
      const detailParts = [];
      if (item.institution) detailParts.push(`<p><strong>Institución:</strong> ${escapeHtml(item.institution)}</p>`);
      if (item.category) detailParts.push(`<p><strong>Categoría:</strong> ${escapeHtml(item.category)}</p>`);
      if (item.impact_summary) detailParts.push(`<p><strong>Resumen de impacto:</strong> ${escapeHtml(item.impact_summary)}</p>`);
      if (item.recommended_action) detailParts.push(`<p><strong>Acción recomendada:</strong> ${escapeHtml(item.recommended_action)}</p>`);
      if (item.risk_if_ignored) detailParts.push(`<p><strong>Riesgo si se ignora:</strong> ${escapeHtml(item.risk_if_ignored)}</p>`);
      if (areas) detailParts.push(`<p><strong>Áreas impactadas:</strong> ${areas}</p>`);
      if (item.agent_reasoning) detailParts.push(`<p><strong>Razonamiento del agente:</strong> ${escapeHtml(item.agent_reasoning)}</p>`);
      if (item.source_url) detailParts.push(`<p><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">Abrir fuente ↗</a></p>`);
      const hasDetail = detailParts.length > 0;
      const main = `
      <tr class="${hasDetail ? "expandable" : ""}" ${hasDetail ? 'data-expand="1"' : ""}>
        <td>${hasDetail ? '<span class="expand-caret">▸</span>' : ""}${escapeHtml(item.presentation_date || "")}</td>
        <td>${escapeHtml(item.title || "")}</td>
        <td>${escapeHtml(item.country || "")}</td>
        <td>${priorityBadge(item.priority)}${review}</td>
        <td class="num">${item.impact_score}</td>
        <td>${confidenceBadge(item.confidence)}</td>
      </tr>`;
      const detail = hasDetail
        ? `<tr class="detail-row" hidden><td colspan="6"><div class="detail-box">${detailParts.join("")}</div></td></tr>`
        : "";
      return main + detail;
    })
    .join("");
}

// ── Historial de ejecuciones del agente ──
async function loadRunHistory() {
  const list = $("#runHistory");
  if (!list) return;
  const preview = $("#runReportPreview");
  const data = await api(`/agent-runs?${companyQuery()}`);
  if (!data.items || !data.items.length) {
    list.innerHTML = `<p class="run-empty">Todavía no corriste el agente. Ejecutalo desde <strong>Configuración</strong> para generar tu primer informe.</p>`;
    if (preview) {
      preview.innerHTML = `<div class="empty-state"><div class="empty-icon">🗂️</div><p class="empty-title">Sin ejecuciones aún.</p></div>`;
      preview.classList.add("is-empty");
    }
    return;
  }
  if (preview && preview.classList.contains("is-empty")) {
    preview.innerHTML = `<div class="empty-state"><div class="empty-icon">👈</div><p class="empty-title">Seleccioná una ejecución para ver su informe.</p></div>`;
  }
  list.innerHTML = data.items
    .map((run) => {
      const fecha = run.started_at
        ? new Date(run.started_at + "Z").toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })
        : "—";
      const email = run.email_sent ? "📧" : "";
      return `
        <button class="run-item" data-run-id="${run.id}">
          <span class="run-date">${escapeHtml(fecha)} ${email}</span>
          <span class="run-meta">${run.fetched || 0} traídas · ${run.evaluated || 0} evaluadas</span>
        </button>`;
    })
    .join("");
}

async function showRunReport(runId, button) {
  const preview = $("#runReportPreview");
  document.querySelectorAll(".run-item").forEach((b) => b.classList.toggle("active", b === button));
  try {
    const md = await api(`/agent-runs/${runId}/report`);
    if (md && md.trim()) {
      preview.innerHTML = markdownToHtml(md);
      preview.classList.remove("is-empty");
    } else {
      preview.innerHTML = `<div class="empty-state"><div class="empty-icon">📄</div><p class="empty-title">Esta corrida no generó alertas nuevas.</p></div>`;
      preview.classList.add("is-empty");
    }
  } catch (e) {
    toast(e.message, "error");
  }
}

const runHistoryEl = $("#runHistory");
if (runHistoryEl) {
  runHistoryEl.addEventListener("click", (event) => {
    const btn = event.target.closest(".run-item");
    if (btn) showRunReport(btn.dataset.runId, btn);
  });
}

async function refreshAll() {
  try {
    await loadCompanies();
    setConnectionError(false);
  } catch (e) {
    console.warn("loadCompanies:", e);
    setConnectionError(true);
    return; // backend caído: no tiene sentido seguir
  }
  await loadFilters().catch((e) => console.warn("loadFilters:", e));
  await loadProfile().catch((e) => console.warn("loadProfile:", e));
  await loadSummary().catch((e) => console.warn("loadSummary:", e));
  await loadAssessments().catch((e) => console.warn("loadAssessments:", e));
  await loadRunHistory().catch((e) => console.warn("loadRunHistory:", e));
  await loadAgentStatus().catch((e) => console.warn("loadAgentStatus:", e));
  await loadAgentSources().catch((e) => console.warn("loadAgentSources:", e));
  checkProgressBanner();
}

// Progress banner
async function checkProgressBanner() {
  try {
    const qs = companyQuery();
    const status = await api(`/onboarding-status${qs ? "?" + qs : ""}`);
    const banner = $("#progress-banner");
    if (status.has_profile && status.alert_count > 0 && status.assessed_count === 0) {
      $("#progress-banner-text").textContent = `Tenés ${status.alert_count} alertas sin evaluar.`;
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch { /* silent */ }
}

$("#progress-banner-btn").addEventListener("click", (event) => {
  const btn = event.currentTarget;
  return withBusy(btn, "Evaluando…", async () => {
    try {
      const qs = companyQuery();
      await api(`/evaluate-alerts${qs ? "?" + qs : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 100 }),
      });
      $("#progress-banner").hidden = true;
      toast("Alertas evaluadas.", "ok");
      await refreshAll();
    } catch (e) {
      console.error(e);
      toast(e.message, "error");
    }
  });
});

// Company selector
$("#companySelect").addEventListener("change", () => {
  const val = $("#companySelect").value;
  if (val) {
    localStorage.setItem("company_id", val);
    refreshAll();
  }
});

$("#newCompanyBtn").addEventListener("click", () => {
  localStorage.removeItem("company_id");
  if (typeof window.__startOnboarding === "function") {
    window.__startOnboarding();
  } else {
    // Fallback: ir a la vista de configuración para cargar el perfil a mano
    switchView("config");
    const input = document.querySelector("#profileForm [name='company_name']");
    if (input) { input.value = ""; input.focus(); }
    console.warn("__startOnboarding not available, falling back to config view");
  }
});

// ── Navegación: menú lateral + vistas ──
const VIEW_TITLES = {
  dashboard: "Dashboard",
  evaluaciones: "Evaluaciones",
  informes: "Informes",
  config: "Configuración",
};

function switchView(view) {
  if (!VIEW_TITLES[view]) view = "dashboard";
  document.querySelectorAll("section.view").forEach((s) => {
    s.classList.toggle("active", s.dataset.view === view);
  });
  document.querySelectorAll(".nav-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === view);
  });
  const title = $("#viewTitle");
  if (title) title.textContent = VIEW_TITLES[view];
  localStorage.setItem("active_view", view);
  closeSidebarDrawer();
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

// ── Sidebar: colapsar (desktop) / drawer (mobile) ──
const sidebar = $("#sidebar");
const sidebarOverlay = $("#sidebarOverlay");

function closeSidebarDrawer() {
  sidebar.classList.remove("open");
  if (sidebarOverlay) sidebarOverlay.hidden = true;
}

$("#sidebarToggle").addEventListener("click", () => {
  if (window.matchMedia("(max-width: 840px)").matches) {
    // Mobile: abrir/cerrar drawer
    const open = !sidebar.classList.contains("open");
    sidebar.classList.toggle("open", open);
    if (sidebarOverlay) sidebarOverlay.hidden = !open;
  } else {
    // Desktop: colapsar a íconos
    const collapsed = sidebar.classList.toggle("collapsed");
    localStorage.setItem("sidebar_collapsed", collapsed);
  }
});

if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebarDrawer);

// Restaurar estado guardado
if (localStorage.getItem("sidebar_collapsed") === "true") {
  sidebar.classList.add("collapsed");
}
switchView(localStorage.getItem("active_view") || "dashboard");

// Custom industry chip (profile form)
$("#addIndustryBtn").addEventListener("click", () => {
  const input = $("#industryCustomInput");
  addCustomIndustryChip("industryChips", input.value);
  input.value = "";
});
$("#industryCustomInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); $("#addIndustryBtn").click(); }
});

// Save profile
$("#profileForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    id: form.dataset.profileId ? Number(form.dataset.profileId) : undefined,
    company_name: form.company_name.value,
    industry: getCheckedIndustries("industryChips"),
    countries: splitList(form.countries.value),
    product_categories: splitList(form.product_categories.value),
    keywords: splitList(form.keywords.value),
    excluded_topics: splitList(form.excluded_topics.value),
    internal_areas: splitList(form.internal_areas.value),
    company_description: form.company_description.value,
    notes: form.notes.value,
  };

  await withBusy(event.submitter, "Guardando…", async () => {
    try {
      const saved = await api("/company-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      localStorage.setItem("company_id", saved.id);
      form.dataset.profileId = saved.id;
      setStatus($("#profileStatus"), "Perfil guardado.");
      await refreshAll();
    } catch (error) {
      setStatus($("#profileStatus"), error.message, false);
    }
  });
});

// Agent panel
async function loadAgentSources() {
  try {
    const data = await api("/alert-sources");
    const container = $("#agentSources");
    if (!data.sources || !data.sources.length) {
      container.innerHTML = `<span class="sources-loading">No se encontraron fuentes. Verificá la conexión a Supabase y las credenciales en <code>.env</code>.</span>`;
      return;
    }
    const savedSources = (await api(`/agent-status?${companyQuery()}`)).alert_sources || [];
    container.innerHTML = data.sources.map((src) => `
      <label class="ob-check agent-source-check">
        <input type="checkbox" value="${escapeHtml(src)}" ${savedSources.includes(src) ? "checked" : ""} />
        ${escapeHtml(src)}
      </label>
    `).join("");
  } catch (e) {
    console.warn("loadAgentSources:", e);
  }
}

function getCheckedSources() {
  return [...document.querySelectorAll("#agentSources input[type=checkbox]:checked")].map((c) => c.value);
}

async function loadAgentStatus() {
  try {
    const qs = companyQuery();
    const status = await api(`/agent-status${qs ? "?" + qs : ""}`);
    const lastRun = status.last_agent_run;
    $("#agentLastRun").textContent = lastRun
      ? new Date(lastRun + "Z").toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })
      : "Nunca";
    const emailsEl = $("#agentEmails");
    if (emailsEl && status.email_recipients) emailsEl.value = (status.email_recipients || []).join(", ");
    const daysEl = $("#agentDaysBack");
    if (daysEl && status.days_back) daysEl.value = status.days_back;
    const maxEvalEl = $("#agentMaxEval");
    if (maxEvalEl && status.agent_max_eval) maxEvalEl.value = status.agent_max_eval;
    const fromEl = $("#agentDateFrom");
    const toEl = $("#agentDateTo");
    if (fromEl) fromEl.value = status.agent_date_from || "";
    if (toEl) toEl.value = status.agent_date_to || "";
    // Si hay una fecha "desde" guardada, el modo activo es rango de fechas.
    const modeEl = $("#agentWindowMode");
    if (modeEl) {
      modeEl.value = status.agent_date_from ? "range" : "days";
      syncAgentWindowMode();
    }
  } catch (e) {
    console.warn("loadAgentStatus:", e);
  }
}

// Muestra los campos según el modo elegido (días relativos vs. rango de fechas).
function syncAgentWindowMode() {
  const isRange = $("#agentWindowMode")?.value === "range";
  const daysField = $("#agentDaysBackField");
  const fromField = $("#agentDateFromField");
  const toField = $("#agentDateToField");
  if (daysField) daysField.hidden = isRange;
  if (fromField) fromField.hidden = !isRange;
  if (toField) toField.hidden = !isRange;
}

$("#agentWindowMode")?.addEventListener("change", syncAgentWindowMode);

// Persiste la config del agente (emails, días, fuentes) que está EN PANTALLA.
// Devuelve true si guardó, false si no hay perfil.
async function persistAgentConfig() {
  const form = $("#profileForm");
  if (!form.dataset.profileId) {
    setStatus($("#agentStatus"), "Guardá primero un perfil de empresa.", false);
    return false;
  }
  const qs = companyQuery();
  const existingProfile = await api(`/company-profile${qs ? "?" + qs : ""}`).catch(() => ({}));
  // En modo "días" se limpia el rango manual; en modo "rango" se guardan las fechas.
  const isRange = $("#agentWindowMode")?.value === "range";
  if (isRange) {
    const from = $("#agentDateFrom").value;
    const to = $("#agentDateTo").value;
    if (!from) {
      setStatus($("#agentStatus"), 'Elegí una fecha "Desde" para el rango, o cambiá a "Últimos N días".', false);
      return false;
    }
    if (to && to < from) {
      setStatus($("#agentStatus"), 'La fecha "Hasta" no puede ser anterior a "Desde".', false);
      return false;
    }
  }
  const payload = {
    ...existingProfile,
    id: Number(form.dataset.profileId),
    email_recipients: splitList($("#agentEmails").value),
    days_back: Number($("#agentDaysBack").value || 7),
    alert_sources: getCheckedSources(),
    agent_date_from: isRange ? ($("#agentDateFrom").value || "") : "",
    agent_date_to: isRange ? ($("#agentDateTo").value || "") : "",
    agent_max_eval: Number($("#agentMaxEval").value || 100),
  };
  await api("/company-profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return true;
}

$("#saveAgentConfigBtn").addEventListener("click", async () => {
  await withBusy($("#saveAgentConfigBtn"), "Guardando…", async () => {
    try {
      if (await persistAgentConfig()) setStatus($("#agentStatus"), "Configuración guardada.");
    } catch (e) {
      setStatus($("#agentStatus"), e.message, false);
    }
  });
});

$("#previewAgentBtn").addEventListener("click", (event) => {
  const btn = event.currentTarget;
  const qs = companyQuery();
  return withBusy(btn, "Calculando…", async () => {
    const box = $("#agentPreview");
    try {
      // Guardar la config en pantalla para que la preview use la ventana/filtros actuales.
      const saved = await persistAgentConfig();
      if (!saved) return;
      const p = await api(`/agent-preview${qs ? "?" + qs : ""}`, { method: "POST" });
      const calls = p.estimated_ai_calls || 0;
      const modeMsg = p.ai_enabled
        ? `<strong>${calls}</strong> llamada${calls === 1 ? "" : "s"} a OpenAI (gasto real de créditos)`
        : `<strong>${calls}</strong> evaluaciones en modo <em>mock</em> (sin costo: no hay OPENAI_API_KEY)`;
      const ceiling = p.hit_fetch_ceiling
        ? `<div class="preview-warn">⚠️ Se alcanzó el tope de ${p.fetched} alertas por corrida; podría haber más en la ventana.</div>`
        : "";
      box.innerHTML = `
        <div class="preview-headline">Si ejecutás ahora: ${modeMsg}</div>
        <ul class="preview-list">
          <li>Alertas que entran por la ventana: <strong>${p.fetched}</strong></li>
          <li>Ya en tu base (se omiten): <strong>${p.already_present}</strong></li>
          <li>Descartadas por el pre-filtro (gratis, sin IA): <strong>${p.would_prefilter}</strong></li>
          <li>Nuevas que pasarían a IA: <strong>${p.would_evaluate_new}</strong></li>
          <li>Pendientes ya en base dentro de la ventana: <strong>${p.pending_local}</strong></li>
          <li>Candidatas totales a evaluar: <strong>${p.candidates_total}</strong> · tope configurado: <strong>${p.cap}</strong></li>
        </ul>
        ${ceiling}`;
      box.hidden = false;
      setStatus($("#agentStatus"), "Previsualización lista (no se gastaron créditos).");
    } catch (e) {
      box.hidden = true;
      setStatus($("#agentStatus"), e.message, false);
    }
  });
});

$("#runAgentBtn").addEventListener("click", (event) => {
  const btn = event.currentTarget;
  const qs = companyQuery();
  return withBusy(btn, "Ejecutando…", async () => {
    try {
      // Guardar primero la selección actual de fuentes/emails/días, así lo que se
      // ejecuta coincide con lo que está tildado en pantalla.
      const saved = await persistAgentConfig();
      if (!saved) return;
      setStatus($("#agentStatus"), "Ejecutando agente… esto puede tomar unos minutos.");
      const result = await api(`/run-agent${qs ? "?" + qs : ""}`, { method: "POST" });
      const r = result.results && result.results[0];
      if (r && r.error) {
        setStatus($("#agentStatus"), `Error: ${r.error}`, false);
      } else if (r) {
        // Mensajes por-paso: Supabase / email
        if (r.supabase_error) {
          setStatus($("#agentStatus"), `Supabase falló: ${r.supabase_error}`, false);
        } else {
          const emailMsg = r.email_sent
            ? "📧 email enviado"
            : (r.email_error ? `email no enviado (${r.email_error})` : "sin email (configurá RESEND_API_KEY)");
          setStatus(
            $("#agentStatus"),
            `Listo: ${r.fetched || 0} alertas traídas, ${r.evaluated || 0} evaluadas — ${emailMsg}`
          );
        }
      }
      await refreshAll();
      await loadAgentStatus();
    } catch (e) {
      setStatus($("#agentStatus"), e.message, false);
    }
  });
});


function markdownToHtml(md) {
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .replace(/^(?!<[h|u|l]).+$/gm, (m) => m.trim() ? `<p>${m}</p>` : "")
    .replace(/\n{2,}/g, "");
}

["dashPriority", "dashCountry", "dashInstitution", "dashReview"].forEach((id) => {
  $(`#${id}`).addEventListener("change", loadAssessments);
});

// Filas expandibles del dashboard (detalle de la evaluación IA)
$("#assessmentRows").addEventListener("click", (event) => {
  if (event.target.closest("a")) return; // no interferir con el link "Abrir"
  const row = event.target.closest("tr.expandable");
  if (!row) return;
  const detail = row.nextElementSibling;
  if (detail && detail.classList.contains("detail-row")) {
    detail.hidden = !detail.hidden;
    const caret = row.querySelector(".expand-caret");
    if (caret) caret.textContent = detail.hidden ? "▸" : "▾";
  }
});

$("#refreshBtn").addEventListener("click", refreshAll);

refreshAll().catch((error) => {
  console.error(error);
});
