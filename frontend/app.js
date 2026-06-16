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

async function loadFilters() {
  state.filters = await api("/filters");
  fillSelect($("#filterCountry"), state.filters.country, "Todos");
  fillSelect($("#filterInstitution"), state.filters.institution, "Todas");
  fillSelect($("#filterCategory"), state.filters.category, "Todas");
  fillSelect($("#dashCountry"), state.filters.country, "Todos");
  fillSelect($("#dashInstitution"), state.filters.institution, "Todas");
}

async function loadProfile() {
  const profile = await api("/company-profile");
  if (!profile.id) return;

  const form = $("#profileForm");
  form.company_name.value = profile.company_name || "";
  form.industry.value = profile.industry || "";
  form.countries.value = (profile.countries || []).join(", ");
  form.product_categories.value = (profile.product_categories || []).join(", ");
  form.keywords.value = (profile.keywords || []).join(", ");
  form.excluded_topics.value = (profile.excluded_topics || []).join(", ");
  form.internal_areas.value = (profile.internal_areas || []).join(", ");
  form.notes.value = profile.notes || "";
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
  const summary = await api("/dashboard-summary");
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
}

function priorityBadge(priority) {
  const value = priority || "no_relevante";
  return `<span class="priority ${value}">${value.replace("_", " ")}</span>`;
}

async function loadAssessments() {
  const params = {
    priority: $("#dashPriority").value,
    country: $("#dashCountry").value,
    institution: $("#dashInstitution").value,
    requires_human_review: $("#dashReview").value,
  };
  const data = await api(`/assessments?${toQuery(params)}`);
  const rows = $("#assessmentRows");

  if (!data.items.length) {
    rows.innerHTML = `<tr><td colspan="10">Todavía no hay evaluaciones para mostrar.</td></tr>`;
    return;
  }

  rows.innerHTML = data.items
    .map((item) => `
      <tr>
        <td>${item.presentation_date || ""}</td>
        <td>${item.country || ""}</td>
        <td>${item.institution || ""}</td>
        <td>${item.title || ""}</td>
        <td>${item.category || ""}</td>
        <td>${priorityBadge(item.priority)}</td>
        <td>${item.impact_score}</td>
        <td>${item.impact_summary || ""}</td>
        <td>${item.recommended_action || ""}</td>
        <td>${item.source_url ? `<a href="${item.source_url}" target="_blank" rel="noreferrer">Abrir</a>` : ""}</td>
      </tr>
    `)
    .join("");
}

async function loadReport() {
  $("#reportText").value = await api("/generate-report");
}

async function refreshAll() {
  await loadFilters();
  await loadProfile();
  await loadSummary();
  await loadAssessments();
  await loadReport();
}

$("#uploadForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#csvFile").files[0];
  if (!file) {
    setStatus($("#uploadStatus"), "Seleccioná un CSV.", false);
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  setStatus($("#uploadStatus"), "Subiendo y procesando CSV...");
  try {
    const result = await api("/upload-csv", { method: "POST", body: formData });
    setStatus(
      $("#uploadStatus"),
      `Listo: ${result.inserted} nuevas, ${result.skipped_duplicates_or_invalid} duplicadas o inválidas.`
    );
    await refreshAll();
  } catch (error) {
    setStatus($("#uploadStatus"), error.message, false);
  }
});

$("#profileForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    company_name: form.company_name.value,
    industry: form.industry.value,
    countries: splitList(form.countries.value),
    product_categories: splitList(form.product_categories.value),
    keywords: splitList(form.keywords.value),
    excluded_topics: splitList(form.excluded_topics.value),
    internal_areas: splitList(form.internal_areas.value),
    notes: form.notes.value,
  };

  try {
    await api("/company-profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus($("#profileStatus"), "Perfil guardado.");
    await refreshAll();
  } catch (error) {
    setStatus($("#profileStatus"), error.message, false);
  }
});

$("#evaluateBtn").addEventListener("click", async () => {
  const payload = {
    ...activeAlertFilters(),
    limit: Number($("#evaluateLimit").value || 100),
  };

  setStatus($("#evaluateStatus"), "Evaluando alertas...");
  try {
    const result = await api("/evaluate-alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus($("#evaluateStatus"), `Evaluación completa: ${result.processed} alertas procesadas.`);
    await refreshAll();
  } catch (error) {
    setStatus($("#evaluateStatus"), error.message, false);
  }
});

$("#downloadReportBtn").addEventListener("click", async () => {
  const markdown = await api("/generate-report");
  $("#reportText").value = markdown;
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `informe-regulatorio-${new Date().toISOString().slice(0, 10)}.md`;
  link.click();
  URL.revokeObjectURL(url);
});

["dashPriority", "dashCountry", "dashInstitution", "dashReview"].forEach((id) => {
  $(`#${id}`).addEventListener("change", loadAssessments);
});

$("#refreshBtn").addEventListener("click", refreshAll);

refreshAll().catch((error) => {
  console.error(error);
});
