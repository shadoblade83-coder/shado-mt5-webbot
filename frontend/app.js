const $ = (id) => document.getElementById(id);

function backendUrl() {
  return $("backendUrl").value.replace(/\/$/, "");
}

function headers() {
  const key = $("apiKey").value.trim();
  return {
    "Content-Type": "application/json",
    ...(key ? { "X-API-Key": key } : {})
  };
}

function botConfig() {
  return {
    symbol: $("symbol").value.trim().toUpperCase(),
    timeframe: $("timeframe").value,
    mode: $("mode").value,
    lot: Number($("lot").value),
    fast_sma: Number($("fastSma").value),
    slow_sma: Number($("slowSma").value),
    stop_loss_points: Number($("slPoints").value),
    take_profit_points: Number($("tpPoints").value),
    max_spread_points: Number($("maxSpread").value),
    max_open_positions: Number($("maxPositions").value),
    loop_seconds: Number($("loopSeconds").value),
  };
}

async function api(path, options = {}) {
  const res = await fetch(`${backendUrl()}${path}`, options);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = text; }
  if (!res.ok) throw new Error(typeof data === "string" ? data : JSON.stringify(data, null, 2));
  return data;
}

function setConnection(ok, text, hint) {
  $("connectionDot").className = `dot ${ok ? "ok" : "bad"}`;
  $("connectionText").textContent = text;
  $("connectionHint").textContent = hint || "";
}

async function checkStatus() {
  try {
    const data = await api("/api/status");
    $("statusBox").textContent = JSON.stringify(data, null, 2);
    setConnection(Boolean(data.connected), data.connected ? "Connected" : "Backend reached", data.error || "MT5 status received");
  } catch (err) {
    $("statusBox").textContent = String(err.message || err);
    setConnection(false, "Offline", "Backend not reachable");
  }
}

async function startBot() {
  try {
    const data = await api("/api/bot/start", { method: "POST", headers: headers(), body: JSON.stringify(botConfig()) });
    $("logsBox").textContent = JSON.stringify(data.logs, null, 2);
  } catch (err) {
    alert(err.message || err);
  }
}

async function stopBot() {
  try {
    const data = await api("/api/bot/stop", { method: "POST", headers: headers() });
    $("logsBox").textContent = JSON.stringify(data.logs, null, 2);
  } catch (err) {
    alert(err.message || err);
  }
}

async function refreshLogs() {
  try {
    const data = await api("/api/bot/state");
    $("logsBox").textContent = JSON.stringify(data.logs, null, 2);
  } catch (err) {
    $("logsBox").textContent = String(err.message || err);
  }
}

async function manualOrder() {
  const config = botConfig();
  const payload = {
    symbol: config.symbol,
    side: $("manualSide").value,
    lot: config.lot,
    stop_loss_points: config.stop_loss_points,
    take_profit_points: config.take_profit_points,
    mode: $("manualMode").value,
  };
  try {
    const data = await api("/api/manual-order", { method: "POST", headers: headers(), body: JSON.stringify(payload) });
    $("logsBox").textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    alert(err.message || err);
  }
}

function drawChart(candles) {
  const canvas = $("chart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!candles.length) return;
  const closes = candles.map(c => c.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const pad = 30;
  const w = canvas.width - pad * 2;
  const h = canvas.height - pad * 2;
  const y = (price) => pad + (max - price) / (max - min || 1) * h;
  const x = (i) => pad + i / Math.max(1, candles.length - 1) * w;

  ctx.strokeStyle = "rgba(255,255,255,.14)";
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i++) {
    const yy = pad + (h / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad, yy); ctx.lineTo(canvas.width - pad, yy); ctx.stroke();
  }

  ctx.strokeStyle = "#2dde72";
  ctx.lineWidth = 2;
  ctx.beginPath();
  closes.forEach((price, i) => {
    if (i === 0) ctx.moveTo(x(i), y(price)); else ctx.lineTo(x(i), y(price));
  });
  ctx.stroke();

  ctx.fillStyle = "#ecfff3";
  ctx.font = "13px system-ui";
  ctx.fillText(`${candles[0].time.slice(0, 10)} → ${candles[candles.length - 1].time.slice(0, 10)}`, pad, 18);
  ctx.fillText(`min ${min.toFixed(5)} | max ${max.toFixed(5)}`, pad, canvas.height - 10);
}

async function loadChart() {
  try {
    const config = botConfig();
    const data = await api(`/api/rates?symbol=${encodeURIComponent(config.symbol)}&timeframe=${config.timeframe}&count=160`);
    drawChart(data.candles);
  } catch (err) {
    alert(err.message || err);
  }
}

$("checkStatusBtn").addEventListener("click", checkStatus);
$("startBotBtn").addEventListener("click", startBot);
$("stopBotBtn").addEventListener("click", stopBot);
$("refreshLogsBtn").addEventListener("click", refreshLogs);
$("manualOrderBtn").addEventListener("click", manualOrder);
$("loadChartBtn").addEventListener("click", loadChart);

checkStatus();
setInterval(refreshLogs, 10000);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("service-worker.js").catch(() => {});
}
