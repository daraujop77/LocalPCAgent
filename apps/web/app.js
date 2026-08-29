const state = {
  base: localStorage.getItem("personal-ai-base") || "http://127.0.0.1:8000",
  token: localStorage.getItem("personal-ai-token") || "",
};

const $ = (id) => document.getElementById(id);
const setText = (element, value) => { element.textContent = value; };

function headers(write = false) {
  const result = { Accept: "application/json" };
  if (state.token) result.Authorization = `Bearer ${state.token}`;
  if (write && state.token) result["X-Personal-AI-CSRF"] = state.token;
  return result;
}

async function request(path, options = {}) {
  const response = await fetch(`${state.base.replace(/\/$/, "")}${path}`, {
    ...options,
    headers: { ...headers(Boolean(options.body)), ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(payload?.details || payload?.error || `HTTP ${response.status}`);
  return payload;
}

function addMessage(role, content, meta = "") {
  const empty = $("chat-log").querySelector(".empty-state");
  if (empty) empty.remove();
  const message = document.createElement("article");
  message.className = `message message-${role}`;
  const label = document.createElement("div");
  label.className = "message-meta";
  label.textContent = meta || (role === "user" ? "You" : "Hermes");
  const body = document.createElement("div");
  body.textContent = content;
  message.append(label, body);
  $("chat-log").append(message);
  message.scrollIntoView({ behavior: "smooth", block: "end" });
}

function renderCards(targetId, records, emptyText, render) {
  const target = $(targetId);
  target.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = emptyText;
    target.append(empty);
    return;
  }
  records.forEach((record) => target.append(render(record)));
}

function card(title, meta, body = "") {
  const element = document.createElement("article");
  element.className = "card";
  const heading = document.createElement("div");
  heading.className = "card-title";
  heading.textContent = title;
  const details = document.createElement("div");
  details.className = "card-meta";
  details.textContent = meta;
  element.append(heading, details);
  if (body) {
    const text = document.createElement("p");
    text.textContent = body;
    element.append(text);
  }
  return element;
}

async function loadHealth() {
  try {
    const payload = await request("/api/v1/health");
    $("health-badge").className = "badge badge-ok";
    setText($("health-badge"), payload.status === "ok" ? "Ready" : "Degraded");
    setText($("system-status"), JSON.stringify(payload, null, 2));
    await loadMonitoring();
  } catch (error) {
    $("health-badge").className = "badge badge-error";
    setText($("health-badge"), "Offline");
    setText($("system-status"), error.message);
  }
}

async function loadMonitoring() {
  const [tools, workflows] = await Promise.all([
    request("/api/v1/tools"),
    request("/api/v1/workflows"),
  ]);
  setText($("tools-status"), JSON.stringify(tools, null, 2));
  setText($("workflows-status"), JSON.stringify(workflows, null, 2));
  const modelCheck = tools?.hermes?.execution || "Local model route unavailable";
  setText($("models-status"), modelCheck);
  setText($("usage-status"), "Run latency and model usage are shown in chat/run records; aggregate metrics are planned.");
}

async function loadRuns() {
  const payload = await request("/api/v1/runs?limit=50");
  renderCards("runs-list", payload.runs || [], "No workflow runs yet.", (run) => {
    const element = card(run.workflow, `${run.status} · ${run.run_id.slice(0, 8)}`, run.current_step || "No active step");
    const actions = document.createElement("div");
    actions.className = "card-actions";
    const events = document.createElement("button");
    events.className = "button button-ghost";
    events.textContent = "Load events";
    events.onclick = () => loadRunEvents(run.run_id);
    actions.append(events);
    const controls = {
      queued: ["cancel"],
      running: ["pause", "steer", "cancel"],
      paused: ["resume", "steer", "cancel"],
      failed: ["retry"],
      interrupted: ["resume", "cancel"],
    }[run.status] || [];
    controls.forEach((control) => {
      const button = document.createElement("button");
      button.className = "button button-ghost";
      button.textContent = control[0].toUpperCase() + control.slice(1);
      button.onclick = async () => {
        const instruction = control === "steer" ? prompt("Steering instruction") : null;
        if (control === "steer" && !instruction?.trim()) return;
        if (control === "cancel" && !confirm("Cancel this workflow run?")) return;
        try {
          await request(`/api/v1/runs/${encodeURIComponent(run.run_id)}/${control}`, {
            method: "POST",
            body: control === "steer" ? JSON.stringify({ instruction }) : "{}",
            headers: { "Content-Type": "application/json" },
          });
          await loadRuns();
        } catch (error) { addMessage("assistant", error.message, "Gateway"); }
      };
      actions.append(button);
    });
    element.append(actions);
    return element;
  });
}

async function loadRunEvents(runId) {
  const payload = await request(`/api/v1/runs/${encodeURIComponent(runId)}/events?limit=100`);
  showView("system");
  setText($("system-status"), JSON.stringify(payload, null, 2));
}

async function loadApprovals() {
  const payload = await request("/api/v1/approvals?limit=50");
  renderCards("approvals-list", payload.approvals || [], "No pending approvals.", (approval) => {
    const element = card(approval.action, `${approval.status} · ${approval.level}`, approval.reason || "");
    if (approval.status === "requested") {
      const actions = document.createElement("div");
      actions.className = "card-actions";
      ["accept", "reject"].forEach((decision) => {
        const button = document.createElement("button");
        button.className = decision === "accept" ? "button button-primary" : "button button-ghost";
        button.textContent = decision[0].toUpperCase() + decision.slice(1);
        button.onclick = async () => {
          try { await request(`/api/v1/approvals/${approval.approval_id}/${decision}`, { method: "POST", body: "{}" }); await loadApprovals(); }
          catch (error) { addMessage("assistant", error.message, "Gateway"); }
        };
        actions.append(button);
      });
      element.append(actions);
    }
    return element;
  });
}

async function loadArtifacts() {
  const payload = await request("/api/v1/artifacts?limit=50");
  renderCards("artifacts-list", payload.artifacts || [], "No artifacts yet.", (artifact) => {
    const element = card(artifact.name, `${artifact.content_type} · ${artifact.size} bytes`, artifact.workflow || "Unassociated artifact");
    const link = document.createElement("a");
    link.href = `${state.base.replace(/\/$/, "")}/api/v1/artifacts/${artifact.artifact_id.split("/").map(encodeURIComponent).join("/")}`;
    link.textContent = "Download";
    link.target = "_blank";
    link.rel = "noopener";
    element.append(link);
    return element;
  });
}

function showView(name) {
  document.querySelectorAll(".view").forEach((view) => view.classList.add("hidden"));
  $(`view-${name}`).classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  if (name === "runs") loadRuns().catch((error) => setText($("runs-list"), error.message));
  if (name === "approvals") loadApprovals().catch((error) => setText($("approvals-list"), error.message));
  if (name === "artifacts") loadArtifacts().catch((error) => setText($("artifacts-list"), error.message));
  if (name === "system") loadHealth();
}

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const field = $("chat-message");
  const message = field.value.trim();
  if (!message) return;
  addMessage("user", message);
  field.value = "";
  try {
    const payload = await request("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, task_type: $("chat-task-type").value }),
    });
    addMessage("assistant", payload.message?.content || payload.error || "No response", `${payload.model_name || "Hermes"} · ${payload.latency_ms || 0} ms`);
  } catch (error) { addMessage("assistant", error.message, "Gateway"); }
});

document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
document.querySelectorAll("[data-refresh]").forEach((item) => item.addEventListener("click", () => showView(item.dataset.refresh)));
$("refresh-chat-health").addEventListener("click", loadHealth);
$("api-base").value = state.base;
$("api-token").value = state.token;
$("save-settings").addEventListener("click", () => {
  state.base = $("api-base").value.trim() || "http://127.0.0.1:8000";
  state.token = $("api-token").value.trim();
  localStorage.setItem("personal-ai-base", state.base);
  localStorage.setItem("personal-ai-token", state.token);
  loadHealth();
});
loadHealth();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("./service-worker.js");
