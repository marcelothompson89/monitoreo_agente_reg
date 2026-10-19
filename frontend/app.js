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

// Adjunta X-API-Key si hay una guardada (localStorage "app_api_key"). Necesario
// cuando el backend corre con APP_API_KEY seteada; en dev local no hace nada.
function withApiKey(options = {}) {
  const key = localStorage.getItem("app_api_key");
  if (!key) return options;
  return { ...options, headers: { ...(options.headers || {}), "X-API-Key": key } };
}

async function api(path, options = {}) {
  const response = await fetch(path, withApiKey(options));
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

// ── Tag input widget (campos de listas: países, categorías, keywords…) ──
// Guarda el array de valores en container._tags; la coma deja de ser un
// separador frágil dentro de un input y los valores se ven como chips.
function getTags(container) {
  return container && container._tags ? container._tags.slice() : [];
}

function renderTagChips(container) {
  const chips = container.querySelector(".tag-chips");
  const tags = container._tags || [];
  chips.innerHTML = tags
    .map((t, i) => `<span class="tag-chip">${escapeHtml(t)}<button type="button" class="tag-remove" data-index="${i}" aria-label="Quitar ${escapeHtml(t)}">✕</button></span>`)
    .join("");
}

function setTags(container, values) {
  if (!container) return;
  const seen = new Set();
  container._tags = [];
  (values || []).forEach((v) => {
    const t = String(v).trim();
    if (t && !seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); container._tags.push(t); }
  });
  renderTagChips(container);
}

// Agrega uno o varios valores (raw puede traer comas: se separan con splitList).
function addTags(container, raw) {
  const incoming = splitList(raw);
  if (!incoming.length) return;
  container._tags = container._tags || [];
  const seen = new Set(container._tags.map((t) => t.toLowerCase()));
  incoming.forEach((t) => {
    if (!seen.has(t.toLowerCase())) { seen.add(t.toLowerCase()); container._tags.push(t); }
  });
  renderTagChips(container);
}

function removeTagAt(container, index) {
  if (!container._tags) return;
  container._tags.splice(index, 1);
  renderTagChips(container);
}

// Delegación de eventos para todos los .tag-input dentro del formulario de perfil.
const profileFormEl = $("#profileForm");
if (profileFormEl) {
  profileFormEl.addEventListener("keydown", (event) => {
    const entry = event.target.closest(".tag-entry");
    if (!entry) return;
    const container = entry.closest(".tag-input");
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      addTags(container, entry.value);
      entry.value = "";
    } else if (event.key === "Backspace" && entry.value === "" && (container._tags || []).length) {
      event.preventDefault();
      removeTagAt(container, container._tags.length - 1);
    }
  });
  // Al salir del campo, consolidar lo que quedó tipeado sin Enter.
  profileFormEl.addEventListener("blur", (event) => {
    const entry = event.target.closest(".tag-entry");
    if (!entry || !entry.value.trim()) return;
    addTags(entry.closest(".tag-input"), entry.value);
    entry.value = "";
  }, true);
  profileFormEl.addEventListener("click", (event) => {
    const remove = event.target.closest(".tag-remove");
    if (remove) {
      removeTagAt(remove.closest(".tag-input"), Number(remove.dataset.index));
      return;
    }
    const add = event.target.closest(".tag-add");
    if (add) {
      const container = add.closest(".tag-input");
      const entry = container.querySelector(".tag-entry");
      addTags(container, entry.value);
      entry.value = "";
      entry.focus();
    }
  });
}

function tagContainer(field) {
  return document.querySelector(`#profileForm .tag-input[data-field="${field}"]`);
}

async function loadProfile() {
  const cid = activeCompanyId();
  const qs = cid ? `?company_id=${cid}` : "";
  const profile = await api(`/company-profile${qs}`);
  if (!profile.id) return;

  const form = $("#profileForm");
  form.company_name.value = profile.company_name || "";
  setCheckedIndustries("industryChips", profile.industry || []);
  setTags(tagContainer("countries"), profile.countries || []);
  setTags(tagContainer("product_categories"), profile.product_categories || []);
  setTags(tagContainer("keywords"), profile.keywords || []);
  setTags(tagContainer("excluded_topics"), profile.excluded_topics || []);
  setTags(tagContainer("internal_areas"), profile.internal_areas || []);
  form.company_description.value = profile.company_description || "";
  form.notes.value = profile.notes || "";

  // Store the profile id for updates
  form.dataset.profileId = profile.id;
}

function toQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  });
  return query.toString();
}

// Rango de fechas elegido en el dashboard (aplica a KPIs y listado).
function dashDateParams() {
  return {
    date_from: $("#dashDateFrom")?.value || "",
    date_to: $("#dashDateTo")?.value || "",
  };
}

async function loadSummary() {
  const params = withCompany({ ...dashDateParams() });
  const summary = await api(`/dashboard-summary?${toQuery(params)}`);
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

// Items de la última carga, indexados para recuperarlos al abrir el drawer.
const assessmentsByIndex = [];

// Arma el HTML del detalle de una evaluación (reutilizado por el drawer lateral).
function renderAssessmentDetail(item) {
  const areas = (item.impacted_areas || []).map(escapeHtml).join(", ");
  const parts = [];
  if (item.institution) parts.push(`<p><strong>Institución:</strong> ${escapeHtml(item.institution)}</p>`);
  if (item.category) parts.push(`<p><strong>Categoría:</strong> ${escapeHtml(item.category)}</p>`);
  if (item.impact_summary) parts.push(`<p><strong>Resumen de impacto:</strong> ${escapeHtml(item.impact_summary)}</p>`);
  if (item.recommended_action) parts.push(`<p><strong>Acción recomendada:</strong> ${escapeHtml(item.recommended_action)}</p>`);
  if (item.risk_if_ignored) parts.push(`<p><strong>Riesgo si se ignora:</strong> ${escapeHtml(item.risk_if_ignored)}</p>`);
  if (areas) parts.push(`<p><strong>Áreas impactadas:</strong> ${areas}</p>`);
  if (item.agent_reasoning) parts.push(`<p><strong>Razonamiento del agente:</strong> ${escapeHtml(item.agent_reasoning)}</p>`);
  if (item.source_url) parts.push(`<p><a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">Abrir fuente ↗</a></p>`);
  if (!parts.length) parts.push(`<p class="detail-empty">Sin detalle adicional para esta alerta.</p>`);
  return `<div class="detail-box">${parts.join("")}</div>`;
}

async function loadAssessments() {
  const params = withCompany({
    priority: $("#dashPriority").value,
    country: $("#dashCountry").value,
    institution: $("#dashInstitution").value,
    requires_human_review: $("#dashReview").value,
    ...dashDateParams(),
  });
  const data = await api(`/assessments?${toQuery(params)}`);
  const rows = $("#assessmentRows");

  assessmentsByIndex.length = 0;

  if (!data.items.length) {
    rows.innerHTML = emptyRow(
      "Todavía no hay evaluaciones para mostrar.",
      'Ejecutá el agente desde <strong>Informes</strong> para generar evaluaciones.'
    );
    return;
  }

  rows.innerHTML = data.items
    .map((item, index) => {
      assessmentsByIndex[index] = item;
      const review = item.requires_human_review
        ? `<span class="review-flag" title="Requiere revisión humana">⚠ Revisión</span>`
        : "";
      return `
      <tr class="assessment-row" data-index="${index}" tabindex="0" role="button" title="Ver detalle">
        <td>${escapeHtml(item.presentation_date || "")}</td>
        <td>${escapeHtml(item.title || "")}</td>
        <td>${escapeHtml(item.country || "")}</td>
        <td>${priorityBadge(item.priority)}${review}</td>
        <td class="num">${item.impact_score}</td>
        <td>${confidenceBadge(item.confidence)}</td>
      </tr>`;
    })
    .join("");
}

// ── Drawer de detalle de alerta ──
function openAlertDrawer(item) {
  const drawer = $("#alertDetailDrawer");
  const overlay = $("#alertDetailOverlay");
  if (!drawer || !overlay) return;
  $("#alertDetailTitle").textContent = item.title || "Detalle de la alerta";
  const meta = [item.country, item.presentation_date].filter(Boolean).join(" · ");
  $("#alertDetailMeta").textContent = meta;
  $("#alertDetailBody").innerHTML = renderAssessmentDetail(item);
  overlay.hidden = false;
  drawer.hidden = false;
  // Forzar reflow para que la transición de entrada se aplique.
  requestAnimationFrame(() => drawer.classList.add("open"));
}

function closeAlertDrawer() {
  const drawer = $("#alertDetailDrawer");
  const overlay = $("#alertDetailOverlay");
  if (!drawer || !overlay) return;
  drawer.classList.remove("open");
  overlay.hidden = true;
  // Esperar a que termine la transición antes de ocultar del layout.
  setTimeout(() => { if (!drawer.classList.contains("open")) drawer.hidden = true; }, 250);
}

// ── Historial de ejecuciones del agente ──
function formatRunDate(value) {
  return value
    ? new Date(value + "Z").toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" })
    : "—";
}

// Tarjeta de estado (vista Agente) + última ejecución (barra de acción de Informes),
// a partir de la corrida más reciente ya traída por /agent-runs.
function renderAgentRunSummary(run) {
  const lastRunEl = $("#informesLastRun");
  const summaryEl = $("#agentRunSummary");
  if (!run) {
    if (lastRunEl) lastRunEl.textContent = "Nunca";
    if (summaryEl) summaryEl.innerHTML = `<p class="run-empty">Todavía no hay ejecuciones registradas.</p>`;
    return;
  }
  const fecha = formatRunDate(run.started_at);
  if (lastRunEl) lastRunEl.textContent = fecha;
  if (summaryEl) {
    summaryEl.innerHTML = `
      <div class="run-summary-grid">
        <div class="run-summary-item"><span class="run-summary-value">${escapeHtml(fecha)}</span><span class="run-summary-label">Última corrida</span></div>
        <div class="run-summary-item"><span class="run-summary-value">${run.fetched || 0}</span><span class="run-summary-label">Alertas traídas</span></div>
        <div class="run-summary-item"><span class="run-summary-value">${run.evaluated || 0}</span><span class="run-summary-label">Evaluadas con IA</span></div>
        <div class="run-summary-item"><span class="run-summary-value">${run.email_sent ? "📧 Enviado" : "No"}</span><span class="run-summary-label">Email</span></div>
      </div>`;
  }
}

async function loadRunHistory() {
  const list = $("#runHistory");
  if (!list) return;
  const preview = $("#runReportPreview");
  const data = await api(`/agent-runs?${companyQuery()}`);
  renderAgentRunSummary(data.items && data.items[0]);
  if (!data.items || !data.items.length) {
    list.innerHTML = `
      <p class="run-empty">Todavía no corriste el agente. Configuralo y ejecutalo para generar tu primer informe.</p>
      <button id="emptyRunAgentBtn" class="secondary">🤖 Ir al agente</button>`;
    list.querySelector("#emptyRunAgentBtn").addEventListener("click", () => switchView("agente"));
    if (preview) {
      preview.innerHTML = `<div class="empty-state"><div class="empty-icon">🗂️</div><p class="empty-title">Sin ejecuciones aún.</p></div>`;
      preview.classList.add("is-empty");
    }
    return;
  }
  list.innerHTML = data.items
    .map((run) => {
      const fecha = formatRunDate(run.started_at);
      const email = run.email_sent ? "📧" : "";
      const window = run.date_from ? `<span class="run-window">ventana desde ${escapeHtml(String(run.date_from).slice(0, 10))}</span>` : "";
      return `
        <div class="run-row">
          <button class="run-item" data-run-id="${run.id}">
            <span class="run-date">${escapeHtml(fecha)} ${email}</span>
            <span class="run-meta">${run.fetched || 0} traídas · ${run.evaluated || 0} evaluadas</span>
            ${window}
          </button>
          <button class="run-delete" data-run-id="${run.id}" title="Eliminar del historial"
                  aria-label="Eliminar del historial el informe del ${escapeHtml(fecha)}">✕</button>
        </div>`;
    })
    .join("");
  // Re-marcar la corrida ya mostrada, o auto-abrir la más reciente para que el
  // usuario vea su último informe sin clicks.
  const selectedId = currentReport ? String(currentReport.runId) : null;
  const target =
    (selectedId && list.querySelector(`.run-item[data-run-id="${selectedId}"]`)) ||
    list.querySelector(".run-item");
  if (!target) return;
  if (selectedId && target.dataset.runId === selectedId) {
    target.classList.add("active");
  } else {
    await showRunReport(target.dataset.runId, target);
  }
}

let currentReport = null; // { runId, html } del informe mostrado, para descargarlo

async function showRunReport(runId, button) {
  const preview = $("#runReportPreview");
  const downloadBtn = $("#downloadReportHtml");
  document.querySelectorAll(".run-item").forEach((b) => b.classList.toggle("active", b === button));
  currentReport = null;
  if (downloadBtn) downloadBtn.hidden = true;
  try {
    // Mismo HTML branded que se envió por email (aislado en un iframe para que
    // sus estilos no se mezclen con los de la app).
    const html = await api(`/agent-runs/${runId}/report.html`);
    if (html && html.trim()) {
      currentReport = { runId, html };
      if (downloadBtn) downloadBtn.hidden = false;
      const iframe = document.createElement("iframe");
      iframe.className = "report-frame";
      iframe.setAttribute("sandbox", "allow-same-origin allow-popups");
      iframe.srcdoc = html;
      // Ajusta la altura del iframe al contenido para que el scroll lo maneje el panel.
      iframe.addEventListener("load", () => {
        try {
          const h = iframe.contentDocument?.body?.scrollHeight;
          if (h) iframe.style.height = `${h + 24}px`;
        } catch (_) { /* cross-origin: se deja la altura por CSS */ }
      });
      preview.replaceChildren(iframe);
      preview.classList.remove("is-empty");
    } else {
      preview.innerHTML = `<div class="empty-state"><div class="empty-icon">📄</div><p class="empty-title">Esta corrida no generó alertas nuevas.</p></div>`;
      preview.classList.add("is-empty");
    }
  } catch (e) {
    toast(e.message, "error");
  }
}

// Baja lógica: el informe deja de listarse pero la corrida queda en la base.
async function deleteRun(runId) {
  if (!confirm("¿Eliminar este informe del historial? Dejará de aparecer en la lista.")) return;
  try {
    await api(`/agent-runs/${runId}`, { method: "DELETE" });
    if (currentReport && String(currentReport.runId) === String(runId)) {
      currentReport = null;
      const downloadBtn = $("#downloadReportHtml");
      if (downloadBtn) downloadBtn.hidden = true;
    }
    toast("Informe eliminado del historial.");
    await loadRunHistory();
  } catch (e) {
    toast(e.message, "error");
  }
}

const runHistoryEl = $("#runHistory");
if (runHistoryEl) {
  runHistoryEl.addEventListener("click", (event) => {
    const del = event.target.closest(".run-delete");
    if (del) {
      deleteRun(del.dataset.runId);
      return;
    }
    const btn = event.target.closest(".run-item");
    if (btn) showRunReport(btn.dataset.runId, btn);
  });
}

const downloadReportBtn = $("#downloadReportHtml");
if (downloadReportBtn) {
  downloadReportBtn.addEventListener("click", () => {
    if (!currentReport) return;
    const blob = new Blob([currentReport.html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `informe-${currentReport.runId}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
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
  informes: "Informes",
  agente: "Agente",
  dashboard: "Dashboard",
  config: "Configuración",
};

function switchView(view) {
  if (!VIEW_TITLES[view]) view = "informes";
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
switchView(localStorage.getItem("active_view") || "informes");

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
    countries: getTags(tagContainer("countries")),
    product_categories: getTags(tagContainer("product_categories")),
    keywords: getTags(tagContainer("keywords")),
    excluded_topics: getTags(tagContainer("excluded_topics")),
    internal_areas: getTags(tagContainer("internal_areas")),
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
// Empresa para la que la grilla de fuentes está cargada (null = no cargada todavía).
// persistAgentConfig solo envía alert_sources cuando coincide con la empresa activa:
// si se guarda mientras /alert-sources sigue cargando (tarda, pagina Supabase) o
// falló, la grilla no tiene checkboxes y getCheckedSources() devolvería [] pisando
// las fuentes guardadas.
let agentSourcesLoadedFor = null;

async function loadAgentSources() {
  const companyId = activeCompanyId();
  agentSourcesLoadedFor = null;
  const container = $("#agentSources");
  container.innerHTML = `<span class="sources-loading">Cargando fuentes…</span>`;
  try {
    const [data, status] = await Promise.all([
      api("/alert-sources"),
      api(`/agent-status?${companyQuery()}`),
    ]);
    // Se cambió de empresa mientras cargaba: la carga nueva se encarga de pintar.
    if (activeCompanyId() !== companyId) return;
    const savedSources = status.alert_sources || [];
    // Las fuentes guardadas que no vienen en la lista disponible se muestran
    // igual (tildadas) para no perderlas al volver a guardar.
    const sources = [...(data.sources || [])];
    savedSources.forEach((src) => { if (!sources.includes(src)) sources.push(src); });
    if (!sources.length) {
      container.innerHTML = `<span class="sources-loading">No se encontraron fuentes. Verificá la conexión a Supabase y las credenciales en <code>.env</code>.</span>`;
      return;
    }
    container.innerHTML = sources.map((src) => `
      <label class="ob-check agent-source-check">
        <input type="checkbox" value="${escapeHtml(src)}" ${savedSources.includes(src) ? "checked" : ""} />
        ${escapeHtml(src)}
      </label>
    `).join("");
    agentSourcesLoadedFor = companyId;
  } catch (e) {
    console.warn("loadAgentSources:", e);
    if (activeCompanyId() === companyId) {
      container.innerHTML = `<span class="sources-loading">No se pudieron cargar las fuentes (${escapeHtml(e.message)}). Las fuentes guardadas no se modifican.</span>`;
    }
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
async function persistAgentConfig(statusEl = $("#agentStatus")) {
  const form = $("#profileForm");
  if (!form.dataset.profileId) {
    setStatus(statusEl, "Guardá primero un perfil de empresa.", false);
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
      setStatus(statusEl, 'Elegí una fecha "Desde" para el rango, o cambiá a "Últimos N días".', false);
      return false;
    }
    if (to && to < from) {
      setStatus(statusEl, 'La fecha "Hasta" no puede ser anterior a "Desde".', false);
      return false;
    }
  }
  const payload = {
    ...existingProfile,
    id: Number(form.dataset.profileId),
    email_recipients: splitList($("#agentEmails").value),
    days_back: Number($("#agentDaysBack").value || 7),
    agent_date_from: isRange ? ($("#agentDateFrom").value || "") : "",
    agent_date_to: isRange ? ($("#agentDateTo").value || "") : "",
    agent_max_eval: Number($("#agentMaxEval").value || 100),
  };
  // Solo pisar las fuentes si la grilla está cargada para esta empresa; si no,
  // se conservan las guardadas (vienen en existingProfile).
  if (agentSourcesLoadedFor === activeCompanyId()) {
    payload.alert_sources = getCheckedSources();
  }
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

// Corre el agente con la config guardada. Compartido por el botón de la vista
// Agente y el quick-run de Informes; statusEl define dónde se muestran los mensajes.
function runAgentNow(button, statusEl) {
  const qs = companyQuery();
  return withBusy(button, "Ejecutando…", async () => {
    try {
      // Guardar primero la selección actual de fuentes/emails/días, así lo que se
      // ejecuta coincide con lo que está tildado en pantalla.
      const saved = await persistAgentConfig(statusEl);
      if (!saved) return;
      setStatus(statusEl, "Ejecutando agente… esto puede tomar unos minutos.");
      const result = await api(`/run-agent${qs ? "?" + qs : ""}`, { method: "POST" });
      const r = result.results && result.results[0];
      let ok = true;
      if (r && r.error) {
        setStatus(statusEl, `Error: ${r.error}`, false);
        ok = false;
      } else if (r) {
        // Mensajes por-paso: Supabase / email
        if (r.supabase_error) {
          setStatus(statusEl, `Supabase falló: ${r.supabase_error}`, false);
          ok = false;
        } else {
          const emailMsg = r.email_sent
            ? "📧 email enviado"
            : (r.email_error ? `email no enviado (${r.email_error})` : "sin email (configurá RESEND_API_KEY)");
          setStatus(
            statusEl,
            `Listo: ${r.fetched || 0} alertas traídas, ${r.evaluated || 0} evaluadas — ${emailMsg}`
          );
        }
      }
      // Soltar el informe seleccionado para que loadRunHistory abra el más nuevo.
      if (ok) currentReport = null;
      await refreshAll();
      await loadAgentStatus();
      if (ok) switchView("informes");
    } catch (e) {
      setStatus(statusEl, e.message, false);
    }
  });
}

$("#runAgentBtn").addEventListener("click", (event) => runAgentNow(event.currentTarget, $("#agentStatus")));
$("#quickRunAgentBtn")?.addEventListener("click", (event) => runAgentNow(event.currentTarget, $("#informesStatus")));
$("#configAgentBtn")?.addEventListener("click", () => switchView("agente"));


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

// El rango de fechas afecta KPIs y listado, así que recarga ambos.
async function reloadDashboardByDate() {
  await loadSummary().catch((e) => console.warn("loadSummary:", e));
  await loadAssessments().catch((e) => console.warn("loadAssessments:", e));
}
["dashDateFrom", "dashDateTo"].forEach((id) => {
  $(`#${id}`)?.addEventListener("change", reloadDashboardByDate);
});
$("#dashClearFilters")?.addEventListener("click", () => {
  ["dashPriority", "dashCountry", "dashInstitution", "dashReview", "dashDateFrom", "dashDateTo"].forEach((id) => {
    const el = $(`#${id}`);
    if (el) el.value = "";
  });
  reloadDashboardByDate();
});

// Clic/Enter en una fila → abrir el drawer con el detalle de la evaluación IA.
function openDrawerFromRow(row) {
  const item = assessmentsByIndex[Number(row.dataset.index)];
  if (item) openAlertDrawer(item);
}

$("#assessmentRows").addEventListener("click", (event) => {
  if (event.target.closest("a")) return; // no interferir con links dentro de la fila
  const row = event.target.closest("tr.assessment-row");
  if (row) openDrawerFromRow(row);
});

$("#assessmentRows").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("tr.assessment-row");
  if (row) {
    event.preventDefault();
    openDrawerFromRow(row);
  }
});

// Cierre del drawer: botón ✕, clic en el overlay y tecla Esc.
$("#alertDetailClose").addEventListener("click", closeAlertDrawer);
$("#alertDetailOverlay").addEventListener("click", closeAlertDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("#alertDetailDrawer").classList.contains("open")) {
    closeAlertDrawer();
  }
});

refreshAll().catch((error) => {
  console.error(error);
});
