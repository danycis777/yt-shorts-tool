const $ = (id) => document.getElementById(id);

async function check() {
  const status = $("status");
  chrome.runtime.sendMessage({ type: "api", path: "/api/status", params: {} }, (res) => {
    if (chrome.runtime.lastError || !res) { status.textContent = "Couldn't reach the extension worker."; status.className = "status bad"; return; }
    if (res.error) { status.textContent = res.error; status.className = "status bad"; return; }
    const d = res.data;
    status.className = "status ok";
    status.textContent = `Connected to ShortsRadar ${d.version}` + (d.youtube_key ? " · YouTube API key set" : " · no YouTube API key (limited data)");
    $("open").href = res.base + "/";
  });
}

chrome.storage.local.get(["port", "enabled"], (v) => {
  $("port").value = v.port || 8765;
  $("enabled").checked = v.enabled !== false;
  $("open").href = `http://127.0.0.1:${v.port || 8765}/`;
  check();
});

$("save").addEventListener("click", () => {
  const port = Math.max(1, Math.min(65535, Number($("port").value) || 8765));
  chrome.storage.local.set({ port, enabled: $("enabled").checked }, () => { $("save").textContent = "Saved ✓"; check(); });
});
$("enabled").addEventListener("change", () => chrome.storage.local.set({ enabled: $("enabled").checked }));
