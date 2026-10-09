const logEl = document.getElementById("log");
const statusEl = document.getElementById("status");
const apiInput = document.getElementById("apiBase");

function log(msg){ if(logEl){ logEl.textContent += msg + "\n"; } }
function getApiBase(){ return localStorage.getItem("VP_API_BASE") || ""; }
function setApiBase(v){ localStorage.setItem("VP_API_BASE", v); }

(function init(){
  const current = getApiBase();
  if(apiInput) apiInput.value = current;
  if(!current){ statusEl.textContent = "Set API Base"; }
})();

document.getElementById("saveApi").onclick = () => {
  const v = apiInput.value.trim();
  setApiBase(v);
  statusEl.textContent = v ? "API saved" : "Set API Base";
  log("Saved API base: " + (v || "<empty>"));
};

document.getElementById("checkApi").onclick = async () => {
  const base = getApiBase();
  if(!base){ log("Set API Base first."); return; }
  try {
    const r = await fetch(base + "/health", { mode: "cors" });
    const j = await r.json();
    log("API /health: " + JSON.stringify(j));
    statusEl.textContent = "API OK";
  } catch (e) {
    log("API check failed: " + e);
    statusEl.textContent = "API error";
  }
};

document.getElementById("openCalendar").onclick = () => {
  window.location.href = "/app/calendar.html";
};

// PWA install prompt support
let deferredPrompt;
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferredPrompt = e; });
document.getElementById("installBtn").onclick = async () => {
  if (!deferredPrompt) return alert("Install not available yet. Try Chrome/Edge on desktop or Android.");
  deferredPrompt.prompt();
  deferredPrompt = null;
};
