function defaultGatewayBase() {
  const hostname = window.location.hostname;
  const isPhonePwa = window.location.port === "4174";
  if (isPhonePwa && hostname && !["127.0.0.1", "localhost", "::1"].includes(hostname)) {
    return `http://${hostname}:8001`;
  }
  return "http://127.0.0.1:8000";
}

const state = {
  base: localStorage.getItem("personal-ai-base") || defaultGatewayBase(),
  token: localStorage.getItem("personal-ai-token") || "",
  chatMode: ["fast", "regular", "deep"].includes(localStorage.getItem("personal-ai-chat-mode"))
    ? localStorage.getItem("personal-ai-chat-mode")
    : "regular",
  reasoningEffort: ["auto", "none", "low", "medium", "high"].includes(localStorage.getItem("personal-ai-reasoning-effort"))
    ? localStorage.getItem("personal-ai-reasoning-effort")
    : "auto",
  responseProfile: ["natural", "technical"].includes(localStorage.getItem("personal-ai-response-profile"))
    ? localStorage.getItem("personal-ai-response-profile")
    : "natural",
  conversationId: null,
  history: [],
  chatMetrics: {
    requests: 0,
    successes: 0,
    failures: 0,
    total_latency_ms: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    last_model: null,
  },
};

const $ = (id) => document.getElementById(id);
const setText = (element, value) => { element.textContent = value; };

const THEME_META = Object.freeze({
  terran: { label: "Terran", title: "Industrial command console" },
  protoss: { label: "Protoss", title: "Geometric energy interface" },
  jarvis: { label: "Jarvis", title: "Holographic assistant interface" },
});

const CHAT_MODE_LABELS = Object.freeze({ fast: "Fast", regular: "Regular", deep: "Deep" });
const REASONING_EFFORT_LABELS = Object.freeze({ auto: "Automatic", none: "Off", low: "Low", medium: "Medium", high: "High" });
const RESPONSE_PROFILE_LABELS = Object.freeze({ natural: "Natural", technical: "Technical" });
const ROUTE_LABELS = Object.freeze({
  "qwen-local": "Local Qwen",
  codex: "Codex",
  grok: "Grok",
  "gemini-optional": "Gemini",
});

function chatModeLabel(mode) {
  return CHAT_MODE_LABELS[mode] || "Regular";
}

function reasoningEffortLabel(effort) {
  return REASONING_EFFORT_LABELS[effort] || "Automatic";
}

function reasoningMeta(payload) {
  const requested = reasoningEffortLabel(payload?.reasoning_effort);
  const effective = payload?.effective_reasoning_effort_label;
  return effective && effective !== requested ? requested + " → " + effective : requested;
}

function responseProfileLabel(profile) {
  return RESPONSE_PROFILE_LABELS[profile] || "Natural";
}

function chatRoutingMeta(payload) {
  const selected = ROUTE_LABELS[payload?.routing?.selected_model] || "Local Qwen";
  const model = payload?.model_name || ROUTE_LABELS[payload?.model] || selected;
  const specialist = payload?.routing?.selected_model && payload.routing.selected_model !== "qwen-local";
  const fallback = payload?.routing?.fallback_used ? " · local fallback" : "";
  const route = specialist ? ` · Hermes → ${selected}${fallback}` : " · Hermes → Local Qwen";
  return `JARVIS · ${model} · ${chatModeLabel(payload?.mode)} · ${reasoningMeta(payload)} reasoning · ${responseProfileLabel(payload?.response_profile)} style${route} · ${payload?.latency_ms || 0} ms`;
}

function chatResponseHint(payload) {
  if (!payload?.success) return "Review the gateway status and try again.";
  const toolResults = Array.isArray(payload.tool_results) ? payload.tool_results : [];
  if (toolResults.some((result) => result?.error === "approval_required")) {
    return "Approval requested. Open Approvals, accept the exact request, then retry the instruction.";
  }
  if (toolResults.some((result) => result?.success && result?.action === "image.generate")) {
    return "Image generated and saved in Artifacts.";
  }
  const selected = ROUTE_LABELS[payload?.routing?.selected_model] || "Local Qwen";
  if (payload?.routing?.fallback_used) {
    return `Hermes selected ${selected}; Local Qwen handled this because that specialist is not configured.`;
  }
  return `Hermes routed this through ${selected}.`;
}

function applyTheme(theme, persist = true) {
  const selected = THEME_META[theme] ? theme : "jarvis";
  document.documentElement.dataset.theme = selected;
  document.body.dataset.theme = selected;
  const selector = $("theme-select");
  if (selector) selector.value = selected;
  if (persist) localStorage.setItem("personal-ai-theme", selected);
}

applyTheme(localStorage.getItem("personal-ai-theme") || document.body.dataset.theme, false);

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

function formatTokenCount(value) {
  const tokens = Number(value) || 0;
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(tokens >= 10_000 ? 0 : 1)}K`;
  return String(tokens);
}

function updateContextUsage(payload = null) {
  const donut = $("context-donut");
  const percent = $("context-percent");
  const label = $("context-usage-label");
  const detail = $("context-usage-detail");
  if (!donut || !percent || !label || !detail) return;
  const usage = payload?.usage || {};
  const promptTokens = Number(usage.prompt_tokens);
  const completionTokens = Number(usage.completion_tokens);
  const contextLimit = Number(usage.context_window_tokens) || 65_536;
  if (!Number.isFinite(promptTokens) || promptTokens < 0) {
    donut.style.setProperty("--context-used", "0%");
    percent.textContent = "0%";
    label.textContent = "No usage yet";
    detail.textContent = `Qwen context window · ${formatTokenCount(contextLimit)} profile`;
    donut.setAttribute("aria-label", "No context usage yet");
    return;
  }
  const usedTokens = Math.max(0, promptTokens + (Number.isFinite(completionTokens) ? completionTokens : 0));
  const usedPercent = Math.min(100, (usedTokens / contextLimit) * 100);
  donut.style.setProperty("--context-used", `${usedPercent.toFixed(2)}%`);
  percent.textContent = `${Math.round(usedPercent)}%`;
  label.textContent = `${formatTokenCount(usedTokens)} / ${formatTokenCount(contextLimit)} tokens`;
  detail.textContent = `Input ${formatTokenCount(promptTokens)} · output ${formatTokenCount(Number.isFinite(completionTokens) ? completionTokens : 0)}`;
  donut.setAttribute("aria-label", `${Math.round(usedPercent)} percent of context used`);
}

async function renderGeneratedImages(payload) {
  const results = Array.isArray(payload?.tool_results) ? payload.tool_results : [];
  for (const result of results) {
    if (!result?.success || result.action !== "image.generate") continue;
    const artifacts = Array.isArray(result.artifacts) ? result.artifacts : [];
    for (const artifactId of artifacts) {
      if (!/\.(png|jpe?g|webp|gif)$/i.test(artifactId)) continue;
      const response = await fetch(artifactUrl(artifactId), { headers: headers(false) });
      if (!response.ok) continue;
      const objectUrl = URL.createObjectURL(await response.blob());
      const message = document.createElement("article");
      message.className = "message message-assistant generated-image-message";
      const label = document.createElement("div");
      label.className = "message-meta";
      label.textContent = `JARVIS · ${result.data?.provider || "image"} · ${result.data?.model || "image model"}`;
      const image = document.createElement("img");
      image.src = objectUrl;
      image.alt = "Image generated by JARVIS";
      image.loading = "lazy";
      const link = document.createElement("a");
      link.className = "generated-image-link";
      link.href = objectUrl;
      link.textContent = "Open generated image";
      link.target = "_blank";
      link.rel = "noopener";
      message.append(label, image, link);
      $("chat-log").append(message);
      message.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }
}

function setCoreState(stateName, signal, caption, hint) {
  const stage = $("jarvis-core-stage");
  if (!stage) return;
  stage.dataset.state = stateName;
  setText($("core-signal"), signal);
  setText($("core-caption-state"), caption);
  setText($("core-caption-hint"), hint);
}

function initCoreMotion() {
  const stage = $("jarvis-core-stage");
  const canvas = stage?.querySelector(".core-motion-layer");
  const context = canvas?.getContext("2d");
  if (!stage || !canvas || !context) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const orbitRadii = [0.18, 0.24, 0.3, 0.36];
  const particleSeeds = Array.from({ length: 18 }, (_, index) => ({
    angle: index * 2.39996,
    radius: orbitRadii[index % orbitRadii.length],
    speed: 0.16 + (index % 5) * 0.035,
    phase: index * 1.73,
  }));
  const activationFlows = [
    { angle: -0.75, radius: 0.13, reach: 0.27, speed: 0.21, twist: 0.8, wave: 0.026, phase: 0.08 },
    { angle: 0.1, radius: 0.14, reach: 0.3, speed: 0.17, twist: -0.72, wave: 0.034, phase: 0.36 },
    { angle: 1.02, radius: 0.12, reach: 0.29, speed: 0.24, twist: 0.62, wave: 0.022, phase: 0.64 },
    { angle: 2.05, radius: 0.15, reach: 0.25, speed: 0.19, twist: -0.9, wave: 0.03, phase: 0.18 },
    { angle: 3.1, radius: 0.13, reach: 0.31, speed: 0.15, twist: 0.68, wave: 0.024, phase: 0.52 },
    { angle: 4.22, radius: 0.14, reach: 0.26, speed: 0.23, twist: -0.64, wave: 0.028, phase: 0.78 },
  ];
  let width = 0;
  let height = 0;
  let pixelRatio = 1;

  function resize() {
    const bounds = canvas.getBoundingClientRect();
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(width * pixelRatio);
    canvas.height = Math.floor(height * pixelRatio);
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  }

  function draw(timestamp = 0) {
    const seconds = timestamp / 1000;
    const centerX = width / 2;
    const centerY = height / 2;
    const unit = Math.min(width, height);
    const stateBoost = stage.dataset.state === "processing" ? 0.12 : stage.dataset.state === "error" ? -0.08 : 0;
    const pulse = (Math.sin(seconds * 1.25) + Math.sin(seconds * 2.7 + 1.1) * 0.32 + 1.32) / 2.64;
    const brightness = Math.max(0.6, Math.min(1.04, 0.67 + pulse * 0.24 + stateBoost));
    const glowOpacity = Math.max(0.48, Math.min(1.08, 0.62 + pulse * 0.3 + stateBoost));
    stage.style.setProperty("--core-brightness", brightness.toFixed(3));
    stage.style.setProperty("--core-glow-opacity", glowOpacity.toFixed(3));

    context.clearRect(0, 0, width, height);
    context.save();
    const aura = context.createRadialGradient(centerX, centerY, unit * 0.03, centerX, centerY, unit * 0.48);
    aura.addColorStop(0, `rgba(131, 239, 255, ${0.12 + pulse * 0.14})`);
    aura.addColorStop(0.45, `rgba(35, 158, 219, ${0.08 + pulse * 0.07})`);
    aura.addColorStop(1, "rgba(4, 30, 55, 0)");
    context.fillStyle = aura;
    context.fillRect(0, 0, width, height);
    context.restore();

    const circularOrbits = [
      { radius: 0.18, start: 0.5, length: 1.4, speed: 0.55, alpha: 0.68 },
      { radius: 0.24, start: 2.8, length: 1.7, speed: -0.4, alpha: 0.58 },
      { radius: 0.3, start: 4.4, length: 1.05, speed: 0.29, alpha: 0.5 },
      { radius: 0.36, start: 1.7, length: 1.9, speed: -0.2, alpha: 0.42 },
      { radius: 0.395, start: 5.2, length: 1.35, speed: 0.16, alpha: 0.4, width: 2.15 },
      { radius: 0.445, start: 2.25, length: 0.95, speed: -0.11, alpha: 0.34, width: 1.85 },
    ];
    circularOrbits.forEach((orbit, index) => {
      context.save();
      context.translate(centerX, centerY);
      context.rotate(orbit.start + seconds * orbit.speed);
      context.beginPath();
      context.arc(0, 0, unit * orbit.radius, 0, orbit.length);
      context.strokeStyle = `rgba(122, 234, 255, ${orbit.alpha * (0.82 + pulse * 0.18)})`;
      context.lineWidth = orbit.width || (index === 0 ? 1.4 : 1);
      context.shadowBlur = 8 + pulse * 6;
      context.shadowColor = "rgba(64, 214, 255, .82)";
      context.stroke();
      context.restore();
    });

    context.save();
    context.globalCompositeOperation = "lighter";
    activationFlows.forEach((flow) => {
      const pointAt = (progress) => {
        const radial = flow.radius + flow.reach * progress;
        const angle = flow.angle + flow.twist * progress + seconds * flow.speed;
        const wave = 1 + flow.wave * Math.sin(progress * Math.PI * 6 + seconds * 2.3 + flow.phase);
        return {
          x: centerX + Math.cos(angle) * unit * radial * wave,
          y: centerY + Math.sin(angle) * unit * radial * wave * 0.78,
        };
      };

      context.beginPath();
      for (let index = 0; index <= 72; index += 1) {
        const point = pointAt(index / 72);
        if (index === 0) context.moveTo(point.x, point.y);
        else context.lineTo(point.x, point.y);
      }
      context.strokeStyle = `rgba(83, 217, 255, ${0.13 + pulse * 0.11})`;
      context.lineWidth = 0.8;
      context.shadowBlur = 7;
      context.shadowColor = "rgba(53, 203, 255, .7)";
      context.stroke();

      const head = (seconds * flow.speed * 0.9 + flow.phase) % 1;
      for (let segment = 0; segment < 11; segment += 1) {
        const progress = head - segment * 0.022;
        if (progress < 0) break;
        const current = pointAt(progress);
        const previous = pointAt(Math.max(0, progress - 0.026));
        const alpha = Math.max(0.04, 0.82 - segment * 0.07) * (0.84 + pulse * 0.16);
        context.beginPath();
        context.moveTo(previous.x, previous.y);
        context.lineTo(current.x, current.y);
        context.strokeStyle = `rgba(204, 250, 255, ${alpha})`;
        context.lineWidth = Math.max(1, 2.8 - segment * 0.16);
        context.shadowBlur = 13 - segment * 0.55;
        context.shadowColor = "rgba(95, 225, 255, .95)";
        context.stroke();
      }
    });
    context.restore();

    context.save();
    context.translate(centerX, centerY);
    context.rotate(seconds * 0.42);
    context.beginPath();
    const thunderPoints = 150;
    for (let index = 0; index <= thunderPoints; index += 1) {
      const theta = (index / thunderPoints) * Math.PI * 2;
      const turbulence = 1 + 0.075 * Math.sin(theta * 5 + seconds * 3.2) + 0.035 * Math.sin(theta * 13 - seconds * 2.4);
      const x = Math.cos(theta) * unit * 0.4 * turbulence;
      const y = Math.sin(theta) * unit * (0.16 + 0.018 * Math.sin(theta * 4 - seconds * 2.1)) * turbulence;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.closePath();
    context.strokeStyle = `rgba(120, 238, 255, ${0.46 + pulse * 0.3})`;
    context.lineWidth = 1.35 + pulse * 0.45;
    context.shadowBlur = 13 + pulse * 12;
    context.shadowColor = "rgba(70, 216, 255, .9)";
    context.stroke();
    context.restore();

    particleSeeds.forEach((particle, index) => {
      const angle = particle.angle + seconds * particle.speed * (index % 2 ? -1 : 1);
      const radius = unit * particle.radius;
      const x = centerX + Math.cos(angle) * radius;
      const y = centerY + Math.sin(angle) * radius * (0.72 + (index % 3) * 0.04);
      const twinkle = 0.52 + 0.34 * ((Math.sin(seconds * 2.1 + particle.phase) + 1) / 2);
      const size = 1.1 + (index % 3) * 0.45;
      context.beginPath();
      context.arc(x, y, size, 0, Math.PI * 2);
      context.fillStyle = `rgba(190, 249, 255, ${twinkle})`;
      context.shadowBlur = 5 + twinkle * 8;
      context.shadowColor = "rgba(95, 225, 255, .95)";
      context.fill();
    });

    if (!reducedMotion) window.requestAnimationFrame(draw);
  }

  resize();
  if (typeof ResizeObserver === "function") new ResizeObserver(resize).observe(canvas);
  else window.addEventListener("resize", resize);
  draw(0);
}

function recordChatResult(payload) {
  const metrics = state.chatMetrics;
  metrics.requests += 1;
  if (payload?.success) metrics.successes += 1;
  else metrics.failures += 1;
  if (Number.isFinite(payload?.latency_ms)) metrics.total_latency_ms += payload.latency_ms;
  if (payload?.mode_label || payload?.mode) {
    metrics.last_model = payload.mode_label || chatModeLabel(payload.mode);
  }
  const usage = payload?.usage || {};
  ["prompt_tokens", "completion_tokens", "total_tokens"].forEach((name) => {
    if (Number.isFinite(usage[name])) metrics[name] += usage[name];
  });
}

function summarizeAgentMetrics(payload) {
  if (payload?.error) return payload;
  const requests = Number(payload?.requests) || 0;
  const fallbackRequests = Number(payload?.fallback_requests) || 0;
  return {
    scope: "aggregate only",
    mode: payload?.mode || "unknown",
    persisted: payload?.persisted === true,
    execution: "plan_only",
    requests,
    successful_requests: Number(payload?.successful_requests) || 0,
    failed_requests: Number(payload?.failed_requests) || 0,
    fallback_requests: fallbackRequests,
    fallback_rate: requests ? `${((fallbackRequests / requests) * 100).toFixed(1)}%` : "0.0%",
    total_steps: Number(payload?.total_steps) || 0,
    average_latency_ms: Number(payload?.average_latency_ms) || 0,
    max_latency_ms: Number(payload?.max_latency_ms) || 0,
    failure_modes: payload?.failure_modes || {},
    by_task_type: payload?.by_task_type || {},
  };
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
    await loadMonitoring(payload);
  } catch (error) {
    $("health-badge").className = "badge badge-error";
    setText($("health-badge"), "Offline");
    setText($("system-status"), error.message);
  }
}

async function loadMonitoring(healthPayload = {}) {
  const results = await Promise.allSettled([
    request("/api/v1/tools"),
    request("/api/v1/workflows"),
    request("/api/v1/system/usage"),
    request("/api/v1/agents/metrics"),
  ]);
  const [toolsResult, workflowsResult, usageResult, agentMetricsResult] = results;
  const failure = (result) => ({ error: result.reason?.message || String(result.reason || "request failed") });
  const tools = toolsResult.status === "fulfilled" ? toolsResult.value : failure(toolsResult);
  const workflows = workflowsResult.status === "fulfilled"
    ? workflowsResult.value
    : failure(workflowsResult);
  const systemUsage = usageResult.status === "fulfilled"
    ? usageResult.value
    : failure(usageResult);
  const agentMetrics = agentMetricsResult.status === "fulfilled"
    ? agentMetricsResult.value
    : failure(agentMetricsResult);
  setText($("tools-status"), JSON.stringify(tools, null, 2));
  setText($("workflows-status"), JSON.stringify(workflows, null, 2));
  const hermes = healthPayload?.checks?.hermes || { status: "unavailable", ready: false };
  setText($("models-status"), JSON.stringify({
    status: hermes.status,
    ready: hermes.ready,
    profiles: hermes.details?.model_profiles,
    routing: "Hermes chooses a specialist from the chat request and falls back to local Qwen when unavailable.",
    tool_execution: hermes.details?.tool_execution,
    conversation_memory: hermes.details?.conversation_memory,
  }, null, 2));
  setText($("usage-status"), JSON.stringify({
    system: systemUsage,
    chat_session: state.chatMetrics,
  }, null, 2));
  setText($("agents-status"), JSON.stringify(summarizeAgentMetrics(agentMetrics), null, 2));
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
  showView("system", { loadSystem: false });
  setText($("system-status"), JSON.stringify(payload, null, 2));
}

function formatScheduleInterval(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "unknown interval";
  const units = [[86400, "day"], [3600, "hour"], [60, "minute"]];
  for (const [size, name] of units) {
    if (value % size === 0) {
      const count = value / size;
      return `every ${count} ${name}${count === 1 ? "" : "s"}`;
    }
  }
  return `every ${value} seconds`;
}

async function loadScheduleEvents(jobId) {
  const payload = await request(`/api/v1/schedules/${encodeURIComponent(jobId)}/events?limit=100`);
  showView("system", { loadSystem: false });
  setText($("system-status"), JSON.stringify(payload, null, 2));
}

async function loadSchedules() {
  const payload = await request("/api/v1/schedules?limit=50");
  renderCards("schedules-list", payload.schedules || [], "No scheduled workflows yet.", (job) => {
    const schedule = job.schedule || {};
    const lastRun = job.last_run_status ? `Last run: ${job.last_run_status}` : "No run yet";
    const retry = job.retry_next_at ? `Retry ${job.retry_attempt || "?"} at ${job.retry_next_at}` : "No retry pending";
    const element = card(
      job.name || job.job_id,
      `${job.status} · ${job.workflow}`,
      `${formatScheduleInterval(schedule.interval_seconds)} · Next: ${job.next_run_at || "not scheduled"} · ${lastRun} · ${retry}`,
    );
    const details = document.createElement("pre");
    details.className = "card-scope";
    details.textContent = JSON.stringify({
      job_id: job.job_id,
      owner: job.owner,
      schedule: {
        kind: schedule.kind,
        interval_seconds: schedule.interval_seconds,
        start_at: schedule.start_at,
      },
      status: job.status,
      next_run_at: job.next_run_at,
      retry_policy: job.retry_policy,
      retry_attempt: job.retry_attempt,
      retry_next_at: job.retry_next_at,
      last_run_at: job.last_run_at,
      last_run_status: job.last_run_status,
      missed_runs: job.missed_runs,
      permission_ceiling: job.permission_ceiling,
      cancellation_policy: job.cancellation_policy,
      overlap_policy: job.overlap_policy,
    }, null, 2);
    element.append(details);

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const events = document.createElement("button");
    events.className = "button button-ghost";
    events.textContent = "Load events";
    events.onclick = () => loadScheduleEvents(job.job_id).catch((error) => addMessage("assistant", error.message, "Gateway"));
    actions.append(events);
    if (job.last_run_id) {
      const runLink = document.createElement("a");
      runLink.className = "button button-ghost";
      runLink.href = "#system";
      runLink.textContent = "Open last run";
      runLink.onclick = (event) => {
        event.preventDefault();
        loadRunEvents(job.last_run_id).catch((error) => addMessage("assistant", error.message, "Gateway"));
      };
      actions.append(runLink);
    }
    const controls = {
      active: ["pause", "cancel"],
      paused: ["resume", "cancel"],
      cancelled: [],
    }[job.status] || [];
    controls.forEach((control) => {
      const button = document.createElement("button");
      button.className = "button button-ghost";
      button.textContent = control[0].toUpperCase() + control.slice(1);
      button.onclick = async () => {
        const label = job.name || job.job_id;
        if (!confirm(`${button.textContent} schedule "${label}"?`)) return;
        try {
          await request(`/api/v1/schedules/${encodeURIComponent(job.job_id)}/${control}`, {
            method: "POST",
            body: "{}",
            headers: { "Content-Type": "application/json" },
          });
          await loadSchedules();
        } catch (error) { addMessage("assistant", error.message, "Gateway"); }
      };
      actions.append(button);
    });
    element.append(actions);
    return element;
  });
}

function renderAgentCatalog(agents) {
  const target = $("agent-catalog");
  target.replaceChildren();
  if (!agents.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No agent catalog returned.";
    target.append(empty);
    return;
  }
  agents.forEach((agent) => {
    const entry = document.createElement("div");
    entry.className = "agent-entry";
    const details = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = agent.name || "unnamed agent";
    const role = document.createElement("small");
    role.textContent = `${agent.role || "Unknown role"} · ${agent.model || "unknown model"}`;
    details.append(name, role);
    const badge = document.createElement("span");
    badge.className = "badge badge-muted";
    badge.textContent = agent.availability || "unknown";
    entry.append(details, badge);
    target.append(entry);
  });
}

function renderAgentPlan(plan) {
  const output = {
    execution: "plan_only",
    status: plan?.status || "planned",
    max_parallelism: plan?.max_parallelism || 1,
    task_type: plan?.task_type || "general",
    steps: plan?.steps || [],
    notes: plan?.notes || [],
  };
  setText($("agent-plan-output"), JSON.stringify(output, null, 2));
}

async function loadAgents() {
  const payload = await request("/api/v1/agents");
  renderAgentCatalog(payload.agents || []);
  const mode = payload.health?.details?.mode || "plan_only";
  setText($("agent-plan-mode"), mode === "plan_only" ? "PLAN ONLY · NO EXECUTION" : mode);
}

async function previewAgentPlan(event) {
  event.preventDefault();
  const task = $("agent-plan-task").value.trim();
  if (!task) return;
  try {
    const plan = await request("/api/v1/agents/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, task_type: $("agent-plan-type").value }),
    });
    renderAgentPlan(plan);
  } catch (error) {
    setText($("agent-plan-output"), error.message);
  }
}

async function loadApprovals() {
  const payload = await request("/api/v1/approvals?limit=50");
  renderCards("approvals-list", payload.approvals || [], "No pending approvals.", (approval) => {
    const element = card(approval.action, `${approval.status} · ${approval.level}`, approval.reason || "");
    const scope = document.createElement("pre");
    scope.className = "card-scope";
    scope.textContent = JSON.stringify({
      target: approval.target,
      parameters: approval.parameters || {},
      scope_digest: approval.scope_digest,
      requested_by: approval.requested_by,
      requested_at: approval.requested_at,
      expires_at: approval.expires_at,
    }, null, 2);
    element.append(scope);
    if (approval.status === "requested") {
      const actions = document.createElement("div");
      actions.className = "card-actions";
      ["accept", "reject"].forEach((decision) => {
        const button = document.createElement("button");
        button.className = decision === "accept" ? "button button-primary" : "button button-ghost";
        button.textContent = decision[0].toUpperCase() + decision.slice(1);
        button.onclick = async () => {
          if (decision === "accept" && !confirm("Approve this exact action, target, and parameter scope?")) return;
          try {
            await request(`/api/v1/approvals/${approval.approval_id}/${decision}`, { method: "POST", body: "{}" });
            if (decision === "accept" && approval.action === "image.generate" && approval.requested_by === "hermes") {
              const result = await request("/api/v1/hermes/tools", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  provider: "image",
                  action: "image.generate",
                  target: approval.target,
                  parameters: { ...(approval.parameters || {}), approval_id: approval.approval_id },
                }),
              });
              addMessage("assistant", result.summary || result.error || "Image request completed.", "JARVIS · Image provider");
              if (result.success) await renderGeneratedImages({ tool_results: [result] });
            }
            await loadApprovals();
          }
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
    const actions = document.createElement("div");
    actions.className = "card-actions";
    const button = document.createElement("button");
    button.className = "button button-ghost";
    button.textContent = "Download";
    button.onclick = async () => {
      try { await downloadArtifact(artifact); }
      catch (error) { addMessage("assistant", error.message, "Gateway"); }
    };
    actions.append(button);
    element.append(actions);
    return element;
  });
}

function artifactUrl(artifactId) {
  const path = artifactId.split("/").map(encodeURIComponent).join("/");
  return `${state.base.replace(/\/$/, "")}/api/v1/artifacts/${path}`;
}

async function downloadArtifact(artifact) {
  const response = await fetch(artifactUrl(artifact.artifact_id), { headers: headers(false) });
  const contentType = response.headers.get("content-type") || "";
  if (!response.ok) {
    const payload = contentType.includes("json") ? await response.json() : await response.text();
    throw new Error(payload?.details || payload?.error || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = artifact.name || "artifact";
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }
}

function showView(name, options = {}) {
  document.querySelectorAll(".view").forEach((view) => view.classList.add("hidden"));
  $(`view-${name}`).classList.remove("hidden");
  document.querySelectorAll("[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  if (name === "runs") loadRuns().catch((error) => setText($("runs-list"), error.message));
  if (name === "schedules") loadSchedules().catch((error) => setText($("schedules-list"), error.message));
  if (name === "agents") loadAgents().catch((error) => setText($("agent-catalog"), error.message));
  if (name === "approvals") loadApprovals().catch((error) => setText($("approvals-list"), error.message));
  if (name === "artifacts") loadArtifacts().catch((error) => setText($("artifacts-list"), error.message));
  if (name === "system" && options.loadSystem !== false) loadHealth();
}

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const field = $("chat-message");
  const message = field.value.trim();
  if (!message) return;
  addMessage("user", message);
  field.value = "";
  setCoreState(
    "processing",
    "PROCESSING",
    "Working on it.",
    `${chatModeLabel(state.chatMode)} mode · Hermes is choosing the best specialist.`,
  );
  try {
    const payload = await request("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode: state.chatMode,
        reasoning_effort: state.reasoningEffort,
        response_profile: state.responseProfile,
        task_type: "auto",
        ...(state.conversationId ? { conversation_id: state.conversationId } : {}),
        ...(state.history.length ? { history: state.history.slice(-20) } : {}),
      }),
    });
    recordChatResult(payload);
    updateContextUsage(payload);
    const reply = payload.message?.content || payload.error || "No response";
    addMessage("assistant", reply, chatRoutingMeta(payload));
    if (payload.success) {
      renderGeneratedImages(payload).catch((error) => addMessage("assistant", error.message, "Gateway"));
    }
    setCoreState(
      payload.success ? "responding" : "error",
      payload.success ? "ACTIVE" : "CHECK",
      payload.success ? "Response ready." : "Gateway needs attention.",
      chatResponseHint(payload),
    );
    if (payload.success && payload.conversation_id) state.conversationId = payload.conversation_id;
    if (payload.success) {
      state.history = [...state.history, { role: "user", content: message }, { role: "assistant", content: reply }].slice(-20);
    }
  } catch (error) {
    state.chatMetrics.requests += 1;
    state.chatMetrics.failures += 1;
    setCoreState("error", "CHECK", "Could not complete that.", "Review the gateway status and try again.");
    addMessage("assistant", error.message, "Gateway");
  }
});

$("agent-plan-form").addEventListener("submit", previewAgentPlan);

document.querySelectorAll("[data-view]").forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
document.querySelectorAll("[data-refresh]").forEach((item) => item.addEventListener("click", () => showView(item.dataset.refresh)));
$("refresh-chat-health").addEventListener("click", loadHealth);
$("api-base").value = state.base;
$("api-token").value = state.token;
$("chat-mode").value = state.chatMode;
setText($("hermes-routing-note"), `Hermes decides the specialist · ${chatModeLabel(state.chatMode)} Qwen · ${responseProfileLabel(state.responseProfile)} style`);
$("chat-mode").addEventListener("change", (event) => {
  state.chatMode = Object.hasOwn(CHAT_MODE_LABELS, event.target.value) ? event.target.value : "regular";
  localStorage.setItem("personal-ai-chat-mode", state.chatMode);
  setText($("hermes-routing-note"), `Hermes decides the specialist · ${chatModeLabel(state.chatMode)} Qwen · ${responseProfileLabel(state.responseProfile)} style`);
});
$("response-profile").value = state.responseProfile;
$("response-profile").addEventListener("change", (event) => {
  state.responseProfile = Object.hasOwn(RESPONSE_PROFILE_LABELS, event.target.value)
    ? event.target.value
    : "natural";
  localStorage.setItem("personal-ai-response-profile", state.responseProfile);
  setText($("hermes-routing-note"), `Hermes decides the specialist · ${chatModeLabel(state.chatMode)} Qwen · ${responseProfileLabel(state.responseProfile)} style`);
});
$("reasoning-effort").value = state.reasoningEffort;
const updateReasoningRoutingNote = () => setText(
  $("hermes-routing-note"),
  "Hermes decides the specialist · " + chatModeLabel(state.chatMode) + " Qwen · " +
    reasoningEffortLabel(state.reasoningEffort) + " reasoning · " +
    responseProfileLabel(state.responseProfile) + " style",
);
$("chat-mode").addEventListener("change", updateReasoningRoutingNote);
$("response-profile").addEventListener("change", updateReasoningRoutingNote);
$("reasoning-effort").addEventListener("change", (event) => {
  state.reasoningEffort = Object.hasOwn(REASONING_EFFORT_LABELS, event.target.value)
    ? event.target.value
    : "auto";
  localStorage.setItem("personal-ai-reasoning-effort", state.reasoningEffort);
  updateReasoningRoutingNote();
});
updateReasoningRoutingNote();
const themeSelect = $("theme-select");
if (themeSelect) themeSelect.addEventListener("change", (event) => applyTheme(event.target.value));
$("save-settings").addEventListener("click", () => {
  state.base = $("api-base").value.trim() || defaultGatewayBase();
  state.token = $("api-token").value.trim();
  state.conversationId = null;
  state.history = [];
  state.chatMetrics = {
    requests: 0,
    successes: 0,
    failures: 0,
    total_latency_ms: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    last_model: null,
  };
  updateContextUsage();
  localStorage.setItem("personal-ai-base", state.base);
  localStorage.setItem("personal-ai-token", state.token);
  loadHealth();
});
initCoreMotion();
loadHealth();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("./service-worker.js");
