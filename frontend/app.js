// JEV Browser Agent Frontend Logic

let currentTaskId = null;
let currentPendingConfirmationId = null;
let ws = null;
let reconnectTimer = null;

// DOM Elements
const taskInput = document.getElementById("taskInput");
const maxStepsInput = document.getElementById("maxStepsInput");
const startBtn = document.getElementById("startBtn");
const pauseBtn = document.getElementById("pauseBtn");
const resumeBtn = document.getElementById("resumeBtn");
const stopBtn = document.getElementById("stopBtn");

const jevModeBadge = document.getElementById("jevModeBadge");
const jevModeText = document.getElementById("jevModeText");
const threshAuto = document.getElementById("threshAuto");
const threshLow = document.getElementById("threshLow");
const wsStatusBadge = document.getElementById("wsStatusBadge");
const wsDot = document.getElementById("wsDot");
const wsStatusText = document.getElementById("wsStatusText");

const agentStatusBadge = document.getElementById("agentStatusBadge");
const stepProgressBadge = document.getElementById("stepProgressBadge");
const browserUrl = document.getElementById("browserUrl");
const browserTitle = document.getElementById("browserTitle");
const currentSubgoalText = document.getElementById("currentSubgoalText");
const liveScreenshot = document.getElementById("liveScreenshot");
const viewportPlaceholder = document.getElementById("viewportPlaceholder");

const activeProviderBadge = document.getElementById("activeProviderBadge");
const selectedActionText = document.getElementById("selectedActionText");
const selectedTargetText = document.getElementById("selectedTargetText");
const confidenceText = document.getElementById("confidenceText");
const confidenceBarFill = document.getElementById("confidenceBarFill");
const decisionReasonText = document.getElementById("decisionReasonText");
const candidatesCount = document.getElementById("candidatesCount");
const candidatesList = document.getElementById("candidatesList");

const approvalBanner = document.getElementById("approvalBanner");
const approvalActionDesc = document.getElementById("approvalActionDesc");
const approvalRiskBadge = document.getElementById("approvalRiskBadge");
const approvalReasonText = document.getElementById("approvalReasonText");

// Metrics
const metricSteps = document.getElementById("metricSteps");
const metricJev = document.getElementById("metricJev");
const metricLlm = document.getElementById("metricLlm");
const metricAvgConf = document.getElementById("metricAvgConf");
const metricDecLatency = document.getElementById("metricDecLatency");
const metricActLatency = document.getElementById("metricActLatency");
const metricSuccess = document.getElementById("metricSuccess");
const metricFailed = document.getElementById("metricFailed");

const actionTimeline = document.getElementById("actionTimeline");

// Initialize application
document.addEventListener("DOMContentLoaded", () => {
  fetchConfig();
  connectWebSocket();
});

// Example Tasks
const EXAMPLES = {
  1: "Open Wikipedia and search for artificial intelligence.",
  2: "Open a search engine and search for Python Playwright.",
  3: "Open a website and find the contact page.",
  4: "Find the official documentation page for FastAPI.",
  5: "Search a shopping website for laptops under ₹50000 and open a matching product."
};

function setExample(num) {
  if (EXAMPLES[num]) {
    taskInput.value = EXAMPLES[num];
    taskInput.focus();
  }
}

// Fetch Public Configuration
async function fetchConfig() {
  try {
    const res = await fetch("/api/config");
    if (res.ok) {
      const data = await res.json();
      jevModeText.textContent = data.jev_mode.toUpperCase() === "REAL" ? "REAL JEV MODE" : "MOCK JEV MODE";
      if (data.jev_mode.toUpperCase() === "REAL") {
        jevModeBadge.classList.add("real-mode");
      }
      threshAuto.textContent = Number(data.auto_execute_threshold).toFixed(2);
      threshLow.textContent = Number(data.low_risk_threshold).toFixed(2);
      if (data.max_steps) {
        maxStepsInput.value = data.max_steps;
      }
    }
  } catch (err) {
    console.warn("Could not fetch config:", err);
  }
}

// WebSocket Connection
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    wsDot.className = "status-dot green";
    wsStatusText.textContent = "Live Connected";
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  ws.onclose = () => {
    wsDot.className = "status-dot red";
    wsStatusText.textContent = "Disconnected";
    reconnectTimer = setTimeout(connectWebSocket, 2500);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    ws.close();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleServerEvent(msg);
    } catch (e) {
      console.warn("Error parsing ws message:", e);
    }
  };
}

// Event Dispatcher
function handleServerEvent(event) {
  const { type, data, metrics, step } = event;

  if (metrics) {
    updateMetrics(metrics);
  }

  if (step !== undefined && step > 0) {
    stepProgressBadge.textContent = `Step ${step} / ${maxStepsInput.value}`;
  }

  const timeStr = new Date().toTimeString().split(" ")[0];

  switch (type) {
    case "TASK_STARTED":
      setAgentStatus("RUNNING", "running");
      appendLog(timeStr, "SYSTEM", `Task started: "${data.prompt}"`, "tag-system");
      if (data.plan && data.plan.subgoals && data.plan.subgoals[0]) {
        currentSubgoalText.textContent = data.plan.subgoals[0];
      }
      break;

    case "PAGE_OPENED":
      browserUrl.value = data.url || "about:blank";
      appendLog(timeStr, "OBSERVE", `Opened ${data.url}`, "tag-observe");
      break;

    case "PAGE_ANALYZED":
      browserUrl.value = data.url || "";
      browserTitle.textContent = data.title || "Untitled";
      appendLog(timeStr, "OBSERVE", `Detected ${data.element_count} interactive elements on "${data.title}"`, "tag-observe");

      if (data.screenshot) {
        liveScreenshot.src = `data:image/jpeg;base64,${data.screenshot}`;
        liveScreenshot.classList.remove("hidden");
        viewportPlaceholder.classList.add("hidden");
      }
      break;

    case "CANDIDATES_FOUND":
      renderCandidates(data.candidates || []);
      break;

    case "JEV_DECISION":
      activeProviderBadge.textContent = (data.provider || "JEV").toUpperCase();
      activeProviderBadge.className = "badge badge-provider";
      selectedActionText.textContent = (data.decision || "-").toUpperCase();
      selectedTargetText.textContent = data.target_id || "viewport";
      decisionReasonText.textContent = data.reason || "";
      appendLog(timeStr, "JEV", `Selected ${data.target_id || 'action'} (${data.decision})`, "tag-jev");
      break;

    case "LLM_FALLBACK":
      activeProviderBadge.textContent = "FALLBACK LLM";
      activeProviderBadge.className = "badge badge-provider";
      appendLog(timeStr, "LLM", `Escalated to Fallback LLM: ${data.reason}`, "tag-llm");
      break;

    case "CONFIDENCE_RESULT":
      renderConfidence(data.confidence);
      appendLog(timeStr, "CONFIDENCE", `${(data.confidence * 100).toFixed(1)}% — ${data.route_note}`, "tag-confidence");
      break;

    case "ACTION_STARTED":
      appendLog(timeStr, "ACTION", `${data.action.toUpperCase()} ${data.target_id || ''} — ${data.description}`, "tag-action");
      break;

    case "ACTION_COMPLETED":
      if (!data.success) {
        appendLog(timeStr, "ACTION", `Warning: ${data.message} (${data.latency_ms}ms)`, "tag-safety");
      }
      break;

    case "VERIFICATION":
      appendLog(timeStr, "VERIFY", data.message, "tag-verify");
      if (data.screenshot) {
        liveScreenshot.src = `data:image/jpeg;base64,${data.screenshot}`;
      }
      break;

    case "HUMAN_CONFIRMATION_REQUIRED":
      setAgentStatus("WAITING APPROVAL", "waiting");
      showApprovalBanner(data);
      appendLog(timeStr, "SAFETY", `Human confirmation requested: ${data.action} (${data.risk_level})`, "tag-safety");
      break;

    case "TASK_PAUSED":
      setAgentStatus("PAUSED", "paused");
      pauseBtn.disabled = true;
      resumeBtn.disabled = false;
      appendLog(timeStr, "SYSTEM", "Execution paused", "tag-system");
      break;

    case "TASK_RESUMED":
      setAgentStatus("RUNNING", "running");
      pauseBtn.disabled = false;
      resumeBtn.disabled = true;
      appendLog(timeStr, "SYSTEM", "Execution resumed", "tag-system");
      break;

    case "TASK_STOPPED":
      setAgentStatus("STOPPED", "failed");
      resetControls();
      appendLog(timeStr, "SYSTEM", "Task stopped by user", "tag-system");
      break;

    case "TASK_COMPLETED":
      setAgentStatus("COMPLETED", "completed");
      resetControls();
      hideApprovalBanner();
      currentSubgoalText.textContent = data.summary || "Task finished.";
      appendLog(timeStr, "SYSTEM", `Completed: ${data.summary}`, "tag-jev");
      break;

    case "TASK_FAILED":
      setAgentStatus("FAILED", "failed");
      resetControls();
      hideApprovalBanner();
      appendLog(timeStr, "SYSTEM", `Error: ${data.error}`, "tag-safety");
      break;
  }
}

// Render Candidate Actions
function renderCandidates(candidates) {
  candidatesCount.textContent = `${candidates.length} candidates`;
  if (!candidates || candidates.length === 0) {
    candidatesList.innerHTML = `<p class="empty-state">No candidates available.</p>`;
    return;
  }

  candidatesList.innerHTML = candidates.map((c, idx) => {
    const scorePct = c.score !== null && c.score !== undefined ? `${(c.score * 100).toFixed(1)}%` : '--';
    const isSelected = idx === 0 ? 'selected' : '';
    const riskBadgeClass = `badge-risk ${(c.risk_level || 'low').toLowerCase()}`;

    return `
      <div class="candidate-item ${isSelected}">
        <div class="cand-left">
          <span class="cand-rank">#${idx + 1}</span>
          <span class="cand-action">${c.action_type}</span>
          <span class="cand-desc" title="${c.description}">${c.description}</span>
        </div>
        <div class="cand-right">
          <span class="${riskBadgeClass}">${c.risk_level}</span>
          <span class="cand-score">${scorePct}</span>
        </div>
      </div>
    `;
  }).join("");
}

// Render Confidence Meter
function renderConfidence(conf) {
  const pct = (conf * 100).toFixed(1);
  confidenceText.textContent = `${pct}%`;
  confidenceBarFill.style.width = `${Math.min(100, Math.max(0, conf * 100))}%`;

  if (conf >= 0.90) {
    confidenceText.style.color = "var(--accent-green)";
    confidenceBarFill.style.background = "linear-gradient(90deg, #10b981, #059669)";
  } else if (conf >= 0.70) {
    confidenceText.style.color = "var(--accent-amber)";
    confidenceBarFill.style.background = "linear-gradient(90deg, #f59e0b, #d97706)";
  } else {
    confidenceText.style.color = "var(--accent-red)";
    confidenceBarFill.style.background = "linear-gradient(90deg, #ef4444, #dc2626)";
  }
}

// Update Performance Metrics
function updateMetrics(m) {
  if (!m) return;
  metricSteps.textContent = m.steps || 0;
  metricJev.textContent = m.jev_decisions || 0;
  metricLlm.textContent = m.llm_fallbacks || 0;
  metricAvgConf.textContent = `${((m.avg_confidence || 0) * 100).toFixed(1)}%`;
  metricDecLatency.textContent = `${Math.round(m.avg_decision_latency_ms || 0)}ms`;
  metricActLatency.textContent = `${Math.round(m.avg_action_latency_ms || 0)}ms`;
  metricSuccess.textContent = m.successful_actions || 0;
  metricFailed.textContent = m.failed_actions || 0;
}

// Append Log Entry
function appendLog(time, tag, msg, tagClass) {
  const row = document.createElement("div");
  row.className = "log-entry";
  row.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-tag ${tagClass}">${tag}</span>
    <span class="log-msg">${escapeHtml(msg)}</span>
  `;
  actionTimeline.appendChild(row);
  actionTimeline.scrollTop = actionTimeline.scrollHeight;
}

function clearLog() {
  actionTimeline.innerHTML = "";
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.innerText = text;
  return div.innerHTML;
}

function setAgentStatus(label, className) {
  agentStatusBadge.textContent = label;
  agentStatusBadge.className = `status-pill ${className}`;
}

// Human Approval UI
function showApprovalBanner(data) {
  currentPendingConfirmationId = data.confirmation_id;
  approvalActionDesc.textContent = data.action;
  approvalRiskBadge.textContent = data.risk_level;
  approvalRiskBadge.className = `badge-risk ${(data.risk_level || 'high').toLowerCase()}`;
  approvalReasonText.textContent = data.reason;
  approvalBanner.classList.remove("hidden");
}

function hideApprovalBanner() {
  approvalBanner.classList.add("hidden");
  currentPendingConfirmationId = null;
}

async function resolveApproval(approve) {
  if (!currentTaskId) return;
  const endpoint = approve ? `/api/tasks/${currentTaskId}/approve` : `/api/tasks/${currentTaskId}/reject`;

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_id: currentPendingConfirmationId })
    });
    if (res.ok) {
      hideApprovalBanner();
      setAgentStatus("RUNNING", "running");
    }
  } catch (err) {
    console.error("Error resolving approval:", err);
  }
}

// Task Lifecycle API calls
async function startTask() {
  const prompt = taskInput.value.trim();
  if (!prompt) {
    alert("Please enter a task description or select an example.");
    return;
  }

  const maxSteps = parseInt(maxStepsInput.value) || 30;

  startBtn.disabled = true;
  pauseBtn.disabled = false;
  resumeBtn.disabled = true;
  stopBtn.disabled = false;

  setAgentStatus("STARTING", "running");
  clearLog();

  try {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, max_steps: maxSteps })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Task creation failed");
    }

    const data = await res.json();
    currentTaskId = data.task_id;
    stepProgressBadge.textContent = `Step 0 / ${maxSteps}`;
  } catch (err) {
    alert(`Failed to start task: ${err.message}`);
    resetControls();
  }
}

async function pauseTask() {
  if (!currentTaskId) return;
  try {
    await fetch(`/api/tasks/${currentTaskId}/pause`, { method: "POST" });
  } catch (e) {
    console.error(e);
  }
}

async function resumeTask() {
  if (!currentTaskId) return;
  try {
    await fetch(`/api/tasks/${currentTaskId}/resume`, { method: "POST" });
  } catch (e) {
    console.error(e);
  }
}

async function stopTask() {
  if (!currentTaskId) return;
  try {
    await fetch(`/api/tasks/${currentTaskId}/stop`, { method: "POST" });
  } catch (e) {
    console.error(e);
  }
}

function resetControls() {
  startBtn.disabled = false;
  pauseBtn.disabled = true;
  resumeBtn.disabled = true;
  stopBtn.disabled = true;
}
