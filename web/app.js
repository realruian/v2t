/* ============================================================
   V2T — queue mode frontend (v2)
   - Pre-transcribe metadata (duration, size) via probe_media()
   - Queue persistence (save_state / load_state)
   - Audio playback in done preview, segment click-to-seek
   - Drag-to-reorder queued items
   ============================================================ */

const $ = (id) => document.getElementById(id);
const body         = document.body;
const addBtn       = $("addBtn");
const language     = $("language");
const pickOutBtn   = $("pickOut");
const outDirShort  = $("outDirShort");
const dropzone     = $("dropzone");
const queueList    = $("queueList");
const queueWrap    = queueList.parentElement;
const stats        = $("stats");
const clearDoneBtn = $("clearDoneBtn");
const cancelAllBtn = $("cancelAllBtn");

// ---------- State ----------
const state = {
  items: [],
  currentId: null,
  language: "auto",
  outputDir: "",
};

const VIDEO_EXT = new Set(["mp4","mov","mkv","avi","webm","flv","wmv","m4v"]);
const SAVE_KEYS = ["language", "outputDir"];

// ---------- Helpers ----------
function fileType(p) {
  const ext = (p.split(".").pop() || "").toLowerCase();
  return VIDEO_EXT.has(ext) ? "video" : "audio";
}
function basename(p) { return p ? p.split("/").pop() : ""; }
function uid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "id-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}
function formatSeconds(s) {
  s = Math.round(s);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m ${String(s%60).padStart(2,"0")}s`;
  return `${Math.floor(s/3600)}h ${String(Math.floor((s%3600)/60)).padStart(2,"0")}m`;
}
function formatHMS(s) {
  s = Math.max(0, s|0);
  const h = Math.floor(s/3600);
  const m = Math.floor((s%3600)/60);
  const sec = s%60;
  if (h) return `${h}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
  return `${m}:${String(sec).padStart(2,"0")}`;
}
function formatBytes(b) {
  if (!b) return "";
  if (b < 1024) return b + " B";
  if (b < 1024*1024) return (b/1024).toFixed(1) + " KB";
  if (b < 1024*1024*1024) return (b/1024/1024).toFixed(1) + " MB";
  return (b/1024/1024/1024).toFixed(2) + " GB";
}
function pathToFileUrl(p) {
  // Encode each segment so spaces / unicode survive WebKit's loader.
  return "file://" + p.split("/").map(encodeURIComponent).join("/");
}
async function waitForApi() {
  while (!(window.pywebview && window.pywebview.api)) {
    await new Promise(r => setTimeout(r, 30));
  }
}

// ---------- Icons ----------
const ICON_AUDIO = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 11v2M21 12h0"/></svg>`;
const ICON_VIDEO = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>`;
const ICON_X     = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>`;
const ICON_RETRY = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15A9 9 0 1 1 5.64 5.64L1 10"/></svg>`;
const ICON_FOLDER = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
const ICON_CHEVRON_DOWN = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;
const ICON_CHEVRON_UP   = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"/></svg>`;
const ICON_GRIP = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/></svg>`;

// ============================================================
// Add files (with metadata probe)
// ============================================================
async function addPaths(paths) {
  if (!paths || !paths.length) return;
  const existing = new Set(state.items.map(x => x.path));
  const newItems = [];
  for (const p of paths) {
    if (!p || existing.has(p)) continue;
    const item = {
      id: uid(),
      path: p,
      name: basename(p),
      type: fileType(p),
      status: "queued",
      expanded: false,
      size: 0,
      sourceDuration: 0,
    };
    state.items.push(item);
    newItems.push(item);
    existing.add(p);
  }
  render();
  saveState();
  scheduleNext();

  // Probe metadata in parallel — render updates on each completion
  await waitForApi();
  await Promise.all(newItems.map(async (it) => {
    try {
      const meta = await window.pywebview.api.probe_media(it.path);
      it.size = meta.size || 0;
      it.sourceDuration = meta.duration || 0;
      // Only re-render if still in queue (not completed/removed)
      if (state.items.includes(it)) {
        renderItem(it);
        saveState();
      }
    } catch {}
  }));
}

addBtn.addEventListener("click", async () => {
  await waitForApi();
  const paths = await window.pywebview.api.pick_files();
  addPaths(paths);
});

// ---------- Output dir ----------
function setOutDir(dir) {
  state.outputDir = dir;
  outDirShort.textContent = basename(dir) || "输出目录";
  pickOutBtn.title = dir;
  saveState();
}
pickOutBtn.addEventListener("click", async () => {
  await waitForApi();
  const p = await window.pywebview.api.pick_output_dir();
  if (p) setOutDir(p);
});

// ---------- Language ----------
language.addEventListener("change", () => {
  state.language = language.value;
  saveState();
});

// ---------- Drag & drop (files) ----------
function attachFileDrop(el) {
  el.addEventListener("dragover", (e) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    el.classList.add(el === dropzone ? "drag" : "drag-over");
  });
  el.addEventListener("dragleave", () => el.classList.remove("drag", "drag-over"));
  el.addEventListener("drop", (e) => {
    if (!e.dataTransfer.files.length) return;
    e.preventDefault();
    el.classList.remove("drag", "drag-over");
    const paths = [];
    for (const f of e.dataTransfer.files) {
      if (f.path) paths.push(f.path);
    }
    addPaths(paths);
  });
}
attachFileDrop(dropzone);
attachFileDrop(queueWrap);

dropzone.addEventListener("click", () => addBtn.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); addBtn.click(); }
});

// ============================================================
// Scheduling
// ============================================================
async function scheduleNext() {
  if (state.currentId) return;
  if (!state.outputDir) return;
  const next = state.items.find(x => x.status === "queued");
  if (!next) return;

  await waitForApi();
  state.currentId = next.id;
  next.status = "running";
  next.progress = 0;
  next.progressLabel = "准备中…";
  next.etaText = "";
  next.indeterminate = true;
  renderItem(next);
  updateStats();
  saveState();

  window.pywebview.api.transcribe(next.path, state.language, state.outputDir);
}
const findItem = (id) => state.items.find(x => x.id === id);
const findCurrent = () => state.currentId ? findItem(state.currentId) : null;

// ============================================================
// Events from Python
// ============================================================
window.__onPyEvent = function (evt) {
  const cur = findCurrent();
  if (!cur) return;
  const { type, payload } = evt;

  if (type === "progress") {
    if (typeof payload === "object" && payload) {
      if ("pct" in payload) {
        cur.indeterminate = false;
        cur.progress = payload.pct;
      } else {
        cur.indeterminate = true;
      }
      if (payload.eta !== undefined) cur.etaText = payload.eta;
      if (payload.label) cur.progressLabel = payload.label;
    } else if (typeof payload === "string") {
      cur.indeterminate = true;
      cur.progressLabel = payload;
    }
    updateRunningItemDom(cur);
  }
  else if (type === "done") {
    cur.status = "done";
    cur.result = payload;
    cur.progress = 100;
    state.currentId = null;
    renderItem(cur);
    updateStats();
    saveState();
    scheduleNext();
  }
  else if (type === "error") {
    cur.status = "error";
    cur.errorMsg = String(payload || "未知错误");
    state.currentId = null;
    renderItem(cur);
    updateStats();
    saveState();
    scheduleNext();
  }
  else if (type === "cancelled") {
    cur.status = "cancelled";
    state.currentId = null;
    renderItem(cur);
    updateStats();
    saveState();
    scheduleNext();
  }
};

// ============================================================
// Item actions
// ============================================================
async function cancelItem(id) {
  if (id !== state.currentId) return;
  await waitForApi();
  await window.pywebview.api.cancel();
}
function removeItem(id) {
  const i = state.items.findIndex(x => x.id === id);
  if (i < 0) return;
  state.items.splice(i, 1);
  render();
  saveState();
}
function retryItem(id) {
  const it = findItem(id);
  if (!it) return;
  it.status = "queued";
  it.errorMsg = undefined;
  it.progress = 0;
  it.expanded = false;
  renderItem(it);
  updateStats();
  saveState();
  scheduleNext();
}
function toggleExpand(id) {
  const it = findItem(id);
  if (!it || it.status !== "done") return;
  it.expanded = !it.expanded;
  renderItem(it);
}
async function revealFile(p) {
  if (!p) return;
  await waitForApi();
  await window.pywebview.api.reveal(p);
}
function copyText(text) {
  navigator.clipboard.writeText(text || "");
  toast("已复制到剪贴板");
}

// ============================================================
// Render
// ============================================================
function render() {
  body.dataset.state = state.items.length ? "hasItems" : "empty";
  queueList.innerHTML = "";
  for (const it of state.items) queueList.appendChild(buildItemNode(it));
  updateStats();
}
function renderItem(item) {
  const old = queueList.querySelector(`[data-id="${item.id}"]`);
  const fresh = buildItemNode(item);
  if (old) {
    // Preserve audio element state if user is playing
    const oldAudio = old.querySelector("audio");
    const newAudio = fresh.querySelector("audio");
    if (oldAudio && newAudio && oldAudio.src === newAudio.src && !oldAudio.paused) {
      newAudio.currentTime = oldAudio.currentTime;
    }
    old.replaceWith(fresh);
  } else queueList.appendChild(fresh);
  body.dataset.state = state.items.length ? "hasItems" : "empty";
}
function updateRunningItemDom(item) {
  const row = queueList.querySelector(`[data-id="${item.id}"]`);
  if (!row) return renderItem(item);
  const fill = row.querySelector(".qi-fill");
  const bar  = row.querySelector(".qi-bar");
  const lbl  = row.querySelector(".qi-progress-label");
  const eta  = row.querySelector(".qi-progress-eta");
  if (!fill || !bar) return renderItem(item);
  if (item.indeterminate) {
    bar.classList.add("indeterminate");
    fill.style.width = "";
  } else {
    bar.classList.remove("indeterminate");
    fill.style.width = `${Math.max(0, Math.min(100, item.progress || 0))}%`;
  }
  if (lbl) lbl.textContent = item.progressLabel || "";
  if (eta) eta.textContent = item.etaText || "";
}

function buildItemNode(item) {
  const li = document.createElement("li");
  li.className = "qi" + (item.expanded ? " expanded" : "");
  li.dataset.id = item.id;
  li.dataset.status = item.status;
  if (item.status === "queued") li.draggable = true;

  const icon = item.type === "video" ? ICON_VIDEO : ICON_AUDIO;
  const badge = badgeHtml(item);
  const actions = actionsHtml(item);

  // sub-line: path + (duration · size) when known
  const subParts = [item.path];
  const metaParts = [];
  if (item.sourceDuration > 0) metaParts.push(formatHMS(item.sourceDuration));
  if (item.size > 0) metaParts.push(formatBytes(item.size));
  if (metaParts.length) subParts.push(metaParts.join(" · "));
  const subLine = subParts.join("  ·  ");

  let progressHtml = "";
  if (item.status === "running") {
    progressHtml = `
      <div class="qi-progress">
        <div class="qi-bar ${item.indeterminate ? "indeterminate" : ""}">
          <div class="qi-fill" style="width:${item.indeterminate ? "" : (item.progress || 0) + "%"}"></div>
        </div>
        <div class="qi-progress-meta">
          <span class="qi-progress-label">${escapeHtml(item.progressLabel || "")}</span>
          <span class="qi-progress-eta">${escapeHtml(item.etaText || "")}</span>
        </div>
      </div>`;
  }

  let errorHtml = "";
  if (item.status === "error" && item.errorMsg) {
    errorHtml = `<div class="qi-error-detail" title="${escapeHtml(item.errorMsg)}">${escapeHtml(item.errorMsg)}</div>`;
  }

  let previewHtml = "";
  if (item.status === "done" && item.result) {
    previewHtml = buildPreviewHtml(item);
  }

  const grip = item.status === "queued" ? `<div class="qi-grip" aria-hidden="true">${ICON_GRIP}</div>` : "";

  li.innerHTML = `
    ${grip}
    <div class="qi-header">
      <div class="qi-icon">${icon}</div>
      <div class="qi-meta">
        <div class="qi-name">${escapeHtml(item.name)}</div>
        <div class="qi-path" title="${escapeHtml(item.path)}">${escapeHtml(subLine)}</div>
      </div>
      <div class="qi-status">${badge}</div>
      <div class="qi-actions">${actions}</div>
    </div>
    ${progressHtml}
    ${errorHtml}
    ${previewHtml}
  `;

  attachItemHandlers(li, item);
  if (item.status === "queued") attachDragHandlers(li, item);
  return li;
}

function buildPreviewHtml(item) {
  const r = item.result || {};
  const segments = Array.isArray(r.segments) ? r.segments : [];
  const langDur = `${r.language || ""} · ${formatSeconds(r.duration || 0)}`;
  const audioUrl = pathToFileUrl(item.path);

  const segHtml = segments.length
    ? segments.map(s => `
        <button class="seg" data-start="${s.start}" type="button">
          <span class="seg-time">${escapeHtml(formatHMS(s.start))}</span>
          <span class="seg-text">${escapeHtml(s.text)}</span>
        </button>`).join("")
    : `<pre class="seg-fallback">${escapeHtml(r.text || "")}</pre>`;

  return `
    <div class="qi-preview">
      <audio class="qi-audio" controls preload="metadata" src="${audioUrl}"></audio>
      <div class="qi-segments">${segHtml}</div>
      <div class="qi-preview-actions">
        <button class="btn small" data-act="copy">复制全文</button>
        <button class="btn small" data-act="export-txt">在 Finder 中显示 TXT</button>
        <button class="btn small" data-act="export-srt">SRT</button>
        <button class="btn small ghost" data-act="export-md">MD</button>
        <span style="flex:1"></span>
        <span class="qi-langdur">${escapeHtml(langDur)}</span>
      </div>
    </div>`;
}

function badgeHtml(item) {
  switch (item.status) {
    case "queued":    return `<span class="qi-badge">等待中</span>`;
    case "running":   return `<span class="qi-badge">转写中</span>`;
    case "done":      return `<span class="qi-badge">✓ 完成</span>`;
    case "error":     return `<span class="qi-badge">⚠ 错误</span>`;
    case "cancelled": return `<span class="qi-badge">已取消</span>`;
    default:          return "";
  }
}
function actionsHtml(item) {
  switch (item.status) {
    case "queued":
      return `<button class="icon-btn" data-act="remove" aria-label="移除">${ICON_X}</button>`;
    case "running":
      return `<button class="btn small" data-act="cancel">取消</button>`;
    case "done":
      return `
        <button class="icon-btn" data-act="reveal" title="在 Finder 中显示" aria-label="在 Finder 中显示">${ICON_FOLDER}</button>
        <button class="icon-btn" data-act="toggle" aria-label="${item.expanded ? "收起" : "展开"}">
          ${item.expanded ? ICON_CHEVRON_UP : ICON_CHEVRON_DOWN}
        </button>
        <button class="icon-btn" data-act="remove" aria-label="移除">${ICON_X}</button>`;
    case "error":
    case "cancelled":
      return `
        <button class="icon-btn" data-act="retry" title="重试" aria-label="重试">${ICON_RETRY}</button>
        <button class="icon-btn" data-act="remove" aria-label="移除">${ICON_X}</button>`;
    default: return "";
  }
}

function attachItemHandlers(row, item) {
  if (item.status === "done") {
    row.querySelector(".qi-header").addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      toggleExpand(item.id);
    });
    // segment click → seek audio
    const audio = row.querySelector("audio");
    row.querySelectorAll(".seg").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!audio) return;
        const t = parseFloat(btn.dataset.start || "0");
        audio.currentTime = t;
        audio.play().catch(() => {});
      });
    });
    if (audio) {
      audio.addEventListener("timeupdate", () => syncSegmentHighlight(row, audio.currentTime));
    }
  }

  row.querySelectorAll("[data-act]").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const act = btn.dataset.act;
      switch (act) {
        case "remove":     removeItem(item.id); break;
        case "cancel":     cancelItem(item.id); break;
        case "retry":      retryItem(item.id); break;
        case "reveal":     revealFile(item.result && item.result.files && item.result.files.txt); break;
        case "toggle":     toggleExpand(item.id); break;
        case "copy":       copyText(item.result && item.result.text); break;
        case "export-txt": revealFile(item.result && item.result.files && item.result.files.txt); break;
        case "export-srt": revealFile(item.result && item.result.files && item.result.files.srt); break;
        case "export-md":  revealFile(item.result && item.result.files && item.result.files.md); break;
      }
    });
  });
}

function syncSegmentHighlight(row, t) {
  const segs = row.querySelectorAll(".seg");
  let activeIdx = -1;
  for (let i = 0; i < segs.length; i++) {
    const start = parseFloat(segs[i].dataset.start || "0");
    if (start <= t) activeIdx = i; else break;
  }
  segs.forEach((s, i) => s.classList.toggle("active", i === activeIdx));
}

// ============================================================
// Drag-to-reorder (queued items only)
// ============================================================
let dragItemId = null;
function attachDragHandlers(li, item) {
  li.addEventListener("dragstart", (e) => {
    dragItemId = item.id;
    li.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    // Setting some data is required by some browsers
    try { e.dataTransfer.setData("text/plain", item.id); } catch {}
  });
  li.addEventListener("dragend", () => {
    dragItemId = null;
    li.classList.remove("dragging");
    queueList.querySelectorAll(".qi.drop-target").forEach(x => x.classList.remove("drop-target"));
  });
  li.addEventListener("dragover", (e) => {
    if (!dragItemId || dragItemId === item.id) return;
    if (item.status !== "queued") return; // only drop onto queued positions
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    li.classList.add("drop-target");
  });
  li.addEventListener("dragleave", () => li.classList.remove("drop-target"));
  li.addEventListener("drop", (e) => {
    if (!dragItemId || dragItemId === item.id) return;
    if (item.status !== "queued") return;
    e.preventDefault();
    e.stopPropagation();
    li.classList.remove("drop-target");
    reorderItem(dragItemId, item.id);
  });
}
function reorderItem(srcId, dstId) {
  const srcIdx = state.items.findIndex(x => x.id === srcId);
  const dstIdx = state.items.findIndex(x => x.id === dstId);
  if (srcIdx < 0 || dstIdx < 0) return;
  const [moved] = state.items.splice(srcIdx, 1);
  const newDst = state.items.findIndex(x => x.id === dstId);
  state.items.splice(newDst, 0, moved);
  render();
  saveState();
}

// ============================================================
// Stats / status bar actions
// ============================================================
function updateStats() {
  const c = { queued:0, running:0, done:0, error:0, cancelled:0 };
  state.items.forEach(x => c[x.status]++);
  if (!state.items.length) {
    stats.textContent = "队列为空";
  } else {
    const parts = [];
    if (c.running)   parts.push(`${c.running} 转写中`);
    if (c.queued)    parts.push(`${c.queued} 等待`);
    if (c.done)      parts.push(`${c.done} 完成`);
    if (c.error)     parts.push(`${c.error} 错误`);
    if (c.cancelled) parts.push(`${c.cancelled} 已取消`);
    stats.textContent = parts.join(" · ");
  }
  clearDoneBtn.hidden = !c.done;
  cancelAllBtn.hidden = !(c.running || c.queued);
}
clearDoneBtn.addEventListener("click", () => {
  state.items = state.items.filter(x => x.status !== "done");
  render();
  saveState();
});
cancelAllBtn.addEventListener("click", async () => {
  if (state.currentId) {
    await waitForApi();
    await window.pywebview.api.cancel();
  }
  state.items = state.items.filter(x => x.status !== "queued");
  render();
  saveState();
});

// ============================================================
// Toast
// ============================================================
let toastTimer = null;
function toast(msg) {
  stats.textContent = msg;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(updateStats, 1600);
}

// ============================================================
// Persistence
// ============================================================
let saveTimer = null;
async function saveState() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    await waitForApi();
    // currentId is meaningless across restarts; drop it
    const snapshot = {
      version: 1,
      language: state.language,
      outputDir: state.outputDir,
      items: state.items.map(it => ({ ...it, expanded: false })),
    };
    try { await window.pywebview.api.save_state(snapshot); } catch {}
  }, 250);
}
async function loadState() {
  await waitForApi();
  let saved = null;
  try { saved = await window.pywebview.api.load_state(); } catch {}
  if (!saved || !saved.items) return false;

  // Sanitize: anything that was running should be re-queued
  for (const it of saved.items) {
    if (it.status === "running") it.status = "queued";
    delete it.indeterminate;
    delete it.progress;
    delete it.progressLabel;
    delete it.etaText;
  }
  state.items    = saved.items;
  state.language = saved.language || "auto";
  state.outputDir = saved.outputDir || state.outputDir;
  language.value = state.language;
  if (state.outputDir) setOutDir(state.outputDir);
  return true;
}

// ============================================================
// Keyboard shortcuts
// ============================================================
document.addEventListener("keydown", (e) => {
  const meta = e.metaKey || e.ctrlKey;
  if (meta && e.key.toLowerCase() === "o") { e.preventDefault(); addBtn.click(); }
});

// ============================================================
// Init
// ============================================================
(async () => {
  await waitForApi();
  state.outputDir = await window.pywebview.api.default_output_dir();
  await loadState(); // may overwrite outputDir / language / items
  if (!state.outputDir) {
    state.outputDir = await window.pywebview.api.default_output_dir();
  }
  setOutDir(state.outputDir);
  language.value = state.language;
  render();
  scheduleNext(); // resume any queued items from previous session
})();
