// Onboarding wizard
(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => [...document.querySelectorAll(sel)];

  const ob = {
    company_name: "", industry: [], description: "",
    countries: [], categories: "", keywords: "", excluded: "", areas: "",
  };

  function showStep(n) {
    $$(".ob-pane").forEach((p) => (p.hidden = true));
    $$(".ob-step").forEach((s) => s.classList.remove("active", "done"));
    $(`#ob-pane-${n}`).hidden = false;
    for (let i = 1; i <= 4; i++) {
      const el = $(`.ob-step[data-step="${i}"]`);
      if (i < n) el.classList.add("done");
      if (i === n) el.classList.add("active");
    }
  }

  function showError(id, msg) {
    const el = $(`#ob-error-${id}`);
    el.textContent = msg;
    el.hidden = false;
  }

  function hideError(id) { $(`#ob-error-${id}`).hidden = true; }

  function getCheckedIndustries() {
    return $$('#ob-industry-grid input[type="checkbox"]:checked').map((c) => c.value);
  }

  // Custom industry chip in onboarding
  function addObIndustryChip(value) {
    if (!value.trim()) return;
    const grid = $("#ob-industry-grid");
    const existing = $$('#ob-industry-grid input[type="checkbox"]').map((c) => c.value);
    if (existing.includes(value.trim())) {
      grid.querySelector(`input[value="${value.trim()}"]`).checked = true;
      return;
    }
    const label = document.createElement("label");
    label.className = "ob-check";
    label.innerHTML = `<input type="checkbox" value="${value.trim()}" checked /> ${value.trim()}`;
    grid.appendChild(label);
  }

  $("#ob-add-industry").addEventListener("click", () => {
    addObIndustryChip($("#ob-industry-custom").value);
    $("#ob-industry-custom").value = "";
  });
  $("#ob-industry-custom").addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); $("#ob-add-industry").click(); }
  });

  // Step 1 → 2
  $("#ob-next-1").addEventListener("click", () => {
    ob.company_name = $("#ob-company-name").value.trim();
    ob.industry = getCheckedIndustries();
    ob.description = $("#ob-description").value.trim();
    if (!ob.company_name) { showError(1, "Ingresá el nombre de la empresa para continuar."); return; }
    hideError(1);
    showStep(2);
  });

  // Step 2 → 3
  $("#ob-next-2").addEventListener("click", () => {
    ob.countries = $$('#ob-countries-grid input[type="checkbox"]:checked').map((c) => c.value);
    ob.categories = $("#ob-categories").value.trim();
    if (!ob.countries.length) { showError(2, "Seleccioná al menos un país."); return; }
    hideError(2);
    showStep(3);
  });

  // Back buttons
  $$(".ob-back").forEach((btn) => {
    btn.addEventListener("click", () => showStep(Number(btn.dataset.target)));
  });

  // Step 3 → 4
  $("#ob-next-3").addEventListener("click", async () => {
    ob.keywords = $("#ob-keywords").value.trim();
    ob.excluded = $("#ob-excluded").value.trim();
    ob.areas = $("#ob-areas").value.trim();

    showStep(4);
    $("#ob-company-display").textContent = ob.company_name;
    $("#ob-loading").hidden = false;
    $("#ob-report-preview").hidden = true;
    $("#ob-nav-4").hidden = true;
    $(`#ob-error-4`).hidden = true;

    try {
      setMsg("Guardando tu perfil de empresa…");
      const saved = await apiFetch("/company-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: ob.company_name,
          industry: ob.industry,
          company_description: ob.description,
          countries: ob.countries,
          product_categories: splitList(ob.categories),
          keywords: splitList(ob.keywords),
          excluded_topics: splitList(ob.excluded),
          internal_areas: splitList(ob.areas),
          notes: "",
        }),
      });

      // Store company id for multi-empresa
      localStorage.setItem("company_id", saved.id);

      $("#ob-loading").hidden = true;
      $("#ob-report-preview").hidden = false;
      $("#ob-nav-4").hidden = false;
    } catch (err) {
      $("#ob-loading").hidden = true;
      const errEl = $(`#ob-error-4`);
      errEl.textContent = "Error: " + err.message;
      errEl.hidden = false;
      $("#ob-nav-4").hidden = false;
    }
  });

  // Finish
  $("#ob-finish").addEventListener("click", () => {
    $("#onboarding-overlay").hidden = true;
    if (typeof refreshAll === "function") refreshAll();
  });

  function setMsg(msg) { $("#ob-loading-msg").textContent = msg; }

  async function apiFetch(path, options = {}) {
    // Adjunta X-API-Key si hay una guardada (backend con APP_API_KEY); en dev no hace nada.
    const key = localStorage.getItem("app_api_key");
    if (key) options = { ...options, headers: { ...(options.headers || {}), "X-API-Key": key } };
    const res = await fetch(path, options);
    if (!res.ok) {
      let msg = "Error desconocido";
      try { const d = await res.json(); msg = d.detail || msg; } catch { msg = await res.text(); }
      throw new Error(msg);
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res.text();
  }

  function splitList(value) {
    return String(value || "").split(",").map((s) => s.trim()).filter(Boolean);
  }

  function startOnboarding() {
    // Reset step 1 fields
    $("#ob-company-name").value = "";
    $$('#ob-industry-grid input[type="checkbox"]').forEach((cb) => cb.checked = false);
    $("#ob-description").value = "";
    $$('#ob-countries-grid input[type="checkbox"]').forEach((cb) => cb.checked = false);
    $("#ob-categories").value = "";
    $("#ob-keywords").value = "";
    $("#ob-excluded").value = "";
    $("#ob-areas").value = "";
    showStep(1);
    $("#onboarding-overlay").hidden = false;
  }

  // Expose for app.js new company button
  window.__startOnboarding = startOnboarding;

  async function init() {
    try {
      const cid = localStorage.getItem("company_id");
      const qs = cid ? `?company_id=${cid}` : "";
      const status = await apiFetch(`/onboarding-status${qs}`);
      if (!status.has_profile) {
        startOnboarding();
      }
    } catch (e) {
      console.error("Onboarding check failed:", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
