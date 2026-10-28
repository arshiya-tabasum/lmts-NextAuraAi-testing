// NextAura AI - AI Appliance Doctor Frontend Controller

let currentStep = 1;
let currentDiagnosis = null;
let leafletMap = null;
let markersGroup = null;

// Initialize on document ready
document.addEventListener("DOMContentLoaded", () => {
  setupApplianceSelection();
  setupDiagnosisForm();
});

function setupApplianceSelection() {
  const cards = document.querySelectorAll(".appliance-select-card");
  cards.forEach(card => {
    card.addEventListener("click", () => {
      cards.forEach(c => c.classList.remove("border-primary", "bg-primary", "text-white", "bg-opacity-10"));
      card.classList.add("border-primary", "bg-primary", "bg-opacity-10");
      const appType = card.getAttribute("data-appliance");
      const input = document.getElementById("selectedApplianceInput");
      if (input) input.value = appType;
      
      // Update quick symptoms suggestions
      populateQuickSymptoms(appType);
    });
  });
}

const SYMPTOM_PRESETS = {
  "Air Conditioners": [
    "AC running but blowing room-temperature air, not cooling",
    "Water dripping constantly from indoor unit wall casing",
    "Loud rattling / buzzing sound coming from outdoor condenser",
    "AC turns on and trips the main circuit breaker after 2 minutes",
    "Flashing LED error code E1 / E4 on the indoor display"
  ],
  "Refrigerators": [
    "Freezer is making ice but lower fridge food compartment is warm",
    "Clicking sound from the back every 2 minutes and compressor stops",
    "Excess water pooling under the vegetable crisper trays",
    "Heavy frost buildup on back wall of the freezer compartment",
    "Fridge door not sealing tight and motor runs continuously"
  ],
  "Washing Machines": [
    "Water not draining and machine halts during spin cycle (Error OE/E20)",
    "Drum makes extreme banging / thumping vibration during high spin",
    "Water filling very slowly through detergent drawer (Error IE/4E)",
    "Drum does not rotate at all even though motor hums",
    "Machine trips electricity as soon as wash cycle begins"
  ]
};

function populateQuickSymptoms(appType) {
  const container = document.getElementById("quickSymptomsContainer");
  if (!container) return;
  container.innerHTML = "";
  const list = SYMPTOM_PRESETS[appType] || SYMPTOM_PRESETS["Air Conditioners"];
  
  list.forEach(s => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "btn btn-sm btn-outline-secondary text-start mb-1 me-1";
    chip.innerText = s;
    chip.onclick = () => {
      const textarea = document.getElementById("symptomsTextarea");
      if (textarea) textarea.value = s;
    };
    container.appendChild(chip);
  });
}

function setupDiagnosisForm() {
  const form = document.getElementById("aiDoctorForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("runDiagnosisBtn");
    const spinner = document.getElementById("diagnosisSpinner");
    
    if (btn) btn.disabled = true;
    if (spinner) spinner.classList.remove("d-none");

    const appType = document.getElementById("selectedApplianceInput").value;
    const brandModel = document.getElementById("brandModelInput").value;
    const symptoms = document.getElementById("symptomsTextarea").value;
    const errorCode = document.getElementById("errorCodeInput").value;

    try {
      const response = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          appliance_type: appType,
          brand_model: brandModel,
          symptoms: symptoms,
          error_code: errorCode
        })
      });

      if (!response.ok) {
        throw new Error("Unable to analyze symptoms. Please check inputs.");
      }

      const data = await response.json();
      currentDiagnosis = data;
      renderDiagnosisResult(data);
      goToStep(2); // Move to Step 2 & 3 preview
    } catch (err) {
      alert(err.message || "Diagnostic failed.");
    } finally {
      if (btn) btn.disabled = false;
      if (spinner) spinner.classList.add("d-none");
    }
  });
}

function renderDiagnosisResult(data) {
  // Populate Symptom Summary
  const summaryEl = document.getElementById("diagSymptomSummary");
  if (summaryEl) summaryEl.innerText = data.symptom_summary;

  // Populate Safe Checks
  const checksList = document.getElementById("diagSafeChecksList");
  if (checksList) {
    checksList.innerHTML = "";
    data.safe_checks.forEach(check => {
      const item = document.createElement("div");
      item.className = "safe-check-item";
      item.innerHTML = `<i class="bi bi-shield-check text-success me-2"></i> ${check}`;
      checksList.appendChild(item);
    });
  }

  // Populate Cost Range & Breakdown
  const costMinEl = document.getElementById("costRangeMin");
  const costMaxEl = document.getElementById("costRangeMax");
  const laborEl = document.getElementById("costLaborBreakdown");
  const partsEl = document.getElementById("costPartsBreakdown");
  const assumptionsEl = document.getElementById("costAssumptions");

  if (costMinEl) costMinEl.innerText = `₹${data.indicative_cost.min_total}`;
  if (costMaxEl) costMaxEl.innerText = `₹${data.indicative_cost.max_total}`;
  if (laborEl) laborEl.innerText = data.indicative_cost.labor_breakdown;
  if (partsEl) partsEl.innerText = data.indicative_cost.parts_breakdown;
  if (assumptionsEl) assumptionsEl.innerText = data.indicative_cost.assumptions;

  // Populate Escalation / Safety Warning
  const warningEl = document.getElementById("diagSafetyWarning");
  if (warningEl) warningEl.innerText = data.safety_warning;

  // Also set hidden values for final booking form
  const hiddenApp = document.getElementById("bookingApplianceType");
  const hiddenBrand = document.getElementById("bookingBrandModel");
  const hiddenSym = document.getElementById("bookingSymptoms");
  const hiddenDiagId = document.getElementById("bookingDiagId");

  if (hiddenApp) hiddenApp.value = data.appliance_type;
  if (hiddenBrand) hiddenBrand.value = data.brand_model;
  if (hiddenSym) hiddenSym.value = data.symptom_summary;
  if (hiddenDiagId) hiddenDiagId.value = data.diagnostic_log_id || "";
}

function goToStep(stepNumber) {
  currentStep = stepNumber;
  
  // Update step indicators
  document.querySelectorAll(".step-node").forEach(node => {
    const s = parseInt(node.getAttribute("data-step"));
    node.classList.remove("active", "completed");
    if (s === stepNumber) {
      node.classList.add("active");
    } else if (s < stepNumber) {
      node.classList.add("completed");
    }
  });

  // Toggle step sections
  document.querySelectorAll(".wizard-step-section").forEach(sec => {
    sec.classList.add("d-none");
  });
  
  const activeSec = document.getElementById(`stepSection${stepNumber}`);
  if (activeSec) {
    activeSec.classList.remove("d-none");
    activeSec.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Initialize Map if navigating to Step 4
  if (stepNumber === 4) {
    setTimeout(initTechniciansMap, 200);
  }
}

function initTechniciansMap() {
  if (leafletMap) {
    leafletMap.invalidateSize();
    return;
  }

  const mapContainer = document.getElementById("mapContainer");
  if (!mapContainer) return;

  // Center around Bengaluru / Indiranagar
  leafletMap = L.map("mapContainer").setView([12.9550, 77.6250], 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: "© OpenStreetMap contributors"
  }).addTo(leafletMap);

  markersGroup = L.featureGroup().addTo(leafletMap);

  // Read technicians embedded in DOM data attributes
  const techCards = document.querySelectorAll(".tech-card-item");
  techCards.forEach(card => {
    const lat = parseFloat(card.getAttribute("data-lat")) || 12.9716;
    const lng = parseFloat(card.getAttribute("data-lng")) || 77.5946;
    const name = card.getAttribute("data-name");
    const locality = card.getAttribute("data-locality");
    const techId = card.getAttribute("data-id");
    const fee = card.getAttribute("data-fee");

    const marker = L.marker([lat, lng]).addTo(markersGroup);
    marker.bindPopup(`
      <div style="font-size:12px; min-width:140px;">
        <strong>${name}</strong><br/>
        <span class="text-success">Verified Specialist</span><br/>
        <span>Locality: ${locality}</span><br/>
        <span>Inspection: ₹${fee}</span><br/>
        <button class="btn btn-primary btn-sm mt-1 w-100" onclick="selectTechnician('${techId}', '${name}', '${fee}')">Select</button>
      </div>
    `);
  });

  if (techCards.length > 0) {
    leafletMap.fitBounds(markersGroup.getBounds().pad(0.2));
  }
}

function selectTechnician(id, name, fee) {
  const input = document.getElementById("selectedTechnicianId");
  if (input) input.value = id;

  const display = document.getElementById("selectedTechBadge");
  if (display) {
    display.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i> Selected: <strong>${name}</strong> (Inspection Fee: ₹${fee})`;
    display.classList.remove("d-none");
  }

  // Highlight card
  document.querySelectorAll(".tech-card-item").forEach(c => {
    c.classList.remove("border-primary", "bg-light");
    if (c.getAttribute("data-id") == id) {
      c.classList.add("border-primary", "bg-light");
    }
  });

  // Enable continue button
  const contBtn = document.getElementById("proceedToBookingBtn");
  if (contBtn) contBtn.disabled = false;
}
