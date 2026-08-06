const DATA_URL = "./data/latest.json";
const state = {
  payload: null,
  filter: "all",
};

const statusText = {
  buy: "买入",
  hold: "持有",
  watch: "观察",
  sell: "卖出",
};

function formatDate(value) {
  if (!value) return "等待数据";
  const date = new Date(value);
  return `更新：${date.toLocaleString("zh-CN", { hour12: false })}`;
}

function formatNumber(value, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toFixed(2)}${suffix}`;
}

function renderSummary(payload) {
  const regime = payload.regime || {};
  document.getElementById("generatedAt").textContent = formatDate(payload.generated_at);
  document.getElementById("regimeLabel").textContent = regime.label || "--";
  document.getElementById("averageScore").textContent = formatNumber(regime.average_score);
  document.getElementById("buyCount").textContent = regime.buy_count ?? "--";
  document.getElementById("sellCount").textContent = regime.sell_count ?? "--";
}

function renderPortfolio(payload) {
  const container = document.getElementById("portfolio");
  const targets = payload.portfolio?.targets || [];
  if (!targets.length) {
    container.innerHTML = `<div class="empty">暂无组合建议。</div>`;
    return;
  }
  container.innerHTML = targets
    .map(
      (item) => `
        <div class="portfolio-row">
          <div>
            <strong>${item.symbol}</strong>
            <span>${item.name}</span>
          </div>
          <b>${formatNumber(item.target_weight_pct, "%")}</b>
        </div>
      `
    )
    .join("");
}

function signalCard(item) {
  const reasons = Array.isArray(item.reasons) ? item.reasons.slice(0, 2).join("；") : "";
  const warnings = Array.isArray(item.warnings) && item.warnings.length ? `风险：${item.warnings[0]}` : "";
  return `
    <article class="signal-card">
      <div class="signal-top">
        <div class="signal-name">
          <span class="symbol">#${item.rank || "--"} · ${item.market.toUpperCase()} · ${item.symbol} · ${item.theme}</span>
          <span class="name">${item.name}</span>
        </div>
        <span class="badge ${item.status}">${statusText[item.status] || item.status}</span>
      </div>
      <div class="score-row">
        <div class="mini"><span>总分</span><strong>${formatNumber(item.score)}</strong></div>
        <div class="mini"><span>20日</span><strong>${formatNumber(item.change_20d_pct, "%")}</strong></div>
        <div class="mini"><span>量能比</span><strong>${formatNumber(item.volume_ratio)}</strong></div>
      </div>
      <p class="reason">${reasons || "暂无理由"}${warnings ? `<br>${warnings}` : ""}<br>数据源：${item.provider || item.data_quality}</p>
    </article>
  `;
}

function renderSignals() {
  const container = document.getElementById("signals");
  const signals = state.payload?.signals || [];
  const filtered = state.filter === "all" ? signals : signals.filter((item) => item.status === state.filter);
  document.getElementById("signalCount").textContent = `${filtered.length} 个`;
  if (!filtered.length) {
    container.innerHTML = `<div class="empty">当前筛选没有信号。</div>`;
    return;
  }
  container.innerHTML = filtered.map(signalCard).join("");
}

async function loadData() {
  const container = document.getElementById("signals");
  container.innerHTML = `<div class="empty">正在读取 latest.json...</div>`;
  try {
    const response = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.payload = await response.json();
    renderSummary(state.payload);
    renderPortfolio(state.payload);
    renderSignals();
  } catch (error) {
    container.innerHTML = `<div class="error">读取数据失败：${error.message}</div>`;
  }
}

function bindEvents() {
  document.getElementById("refreshButton").addEventListener("click", loadData);
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      state.filter = button.dataset.filter;
      renderSignals();
    });
  });
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}

bindEvents();
loadData();
