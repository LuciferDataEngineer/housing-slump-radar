const pageId = document.body.dataset.page;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function badge(status) {
  const label = { act: "Act", watch: "Watch", good: "Good" }[status] || status;
  return el("span", `badge ${status}`, label);
}

function renderStats(stats) {
  if (!stats || !stats.length) return null;
  const grid = el("section", "stats");
  stats.forEach((stat) => {
    const card = el("article", `stat ${stat.status}`);
    card.append(el("p", "label", stat.label), el("p", "value", stat.value), el("p", "detail", stat.detail));
    grid.append(card);
  });
  return grid;
}

function renderLine(chart) {
  const panel = el("section", "panel");
  panel.append(el("h2", null, chart.title));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 720 230");
  svg.setAttribute("class", "line");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", chart.title);
  const points = chart.points;
  const ys = points.map((point) => point.y);
  let min = Math.min(...ys);
  let max = Math.max(...ys);
  const pad = (max - min) * 0.25 || 0.25;
  min -= pad;
  max += pad;
  const left = 36;
  const right = 688;
  const top = 18;
  const bottom = 188;
  const xAt = (index) => left + (index * (right - left)) / Math.max(points.length - 1, 1);
  const yAt = (value) => top + ((max - value) * (bottom - top)) / (max - min);
  const coords = points.map((point, index) => `${xAt(index)},${yAt(point.y)}`).join(" ");
  const path = document.createElementNS(svg.namespaceURI, "polyline");
  path.setAttribute("points", coords);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "#1e3a5f");
  path.setAttribute("stroke-width", "3");
  svg.append(path);
  points.forEach((point, index) => {
    if (!point.marker) return;
    const dot = document.createElementNS(svg.namespaceURI, "circle");
    dot.setAttribute("cx", xAt(index));
    dot.setAttribute("cy", yAt(point.y));
    dot.setAttribute("r", index === points.length - 1 ? 5 : 3.5);
    dot.setAttribute("fill", "#9f1239");
    svg.append(dot);
    if (!point.label) return;
    const text = document.createElementNS(svg.namespaceURI, "text");
    text.setAttribute("x", xAt(index));
    text.setAttribute("y", index === points.length - 1 ? yAt(point.y) - 10 : 214);
    text.setAttribute("text-anchor", index === points.length - 1 ? "end" : "middle");
    text.textContent = point.label;
    svg.append(text);
  });
  panel.append(svg);
  return panel;
}

function renderDiverge(chart) {
  const panel = el("section", "panel");
  panel.append(el("h2", null, chart.title));
  const scale = Math.max(...chart.items.map((item) => Math.abs(item.value)), 1);
  chart.items.forEach((item) => {
    const row = el("div", "diverge-row");
    const track = el("div", "track");
    track.append(el("span", "zero"));
    const bar = el("span", `bar ${item.status}`);
    const width = `${(Math.abs(item.value) / scale) * 50}%`;
    bar.style.width = width;
    if (item.value < 0) bar.style.right = "50%";
    else bar.style.left = "50%";
    track.append(bar);
    row.append(el("span", null, item.label), track, el("span", "value", item.display));
    panel.append(row);
  });
  return panel;
}

function renderCompare(chart) {
  const panel = el("section", "panel");
  panel.append(el("h2", null, chart.title));
  const max = Math.max(...chart.items.map((item) => item.value), 1);
  chart.items.forEach((item) => {
    const row = el("div", "compare-row");
    const track = el("div", "track");
    const bar = el("span", `bar compare ${item.status}`);
    bar.style.width = `${(item.value / max) * 100}%`;
    track.append(bar);
    row.append(el("span", null, item.label), track, el("span", "value", item.display));
    panel.append(row);
  });
  return panel;
}

function renderChart(chart) {
  if (chart.kind === "line") return renderLine(chart);
  if (chart.kind === "diverge") return renderDiverge(chart);
  if (chart.kind === "compare") return renderCompare(chart);
  return null;
}

function renderTable(table) {
  if (!table) return null;
  const panel = el("section", "panel");
  panel.append(el("h2", null, table.caption));
  const grid = el("table");
  const head = el("tr");
  table.columns.forEach((column) => head.append(el("th", null, column)));
  grid.append(head);
  table.rows.forEach((row) => {
    const line = el("tr");
    row.forEach((cell) => line.append(el("td", null, String(cell))));
    grid.append(line);
  });
  panel.append(grid);
  return panel;
}

function renderCards(cards) {
  if (!cards) return null;
  const grid = el("section", "cards");
  cards.forEach((card) => {
    const block = el("article", `card ${card.status}`);
    block.append(el("p", "kicker", card.kicker), el("h3", null, card.title), el("p", null, card.body));
    grid.append(block);
  });
  return grid;
}

function renderCallout(callout) {
  if (!callout) return null;
  const block = el("aside", "callout");
  block.append(badge(callout.status), el("h2", null, callout.title), el("p", null, callout.body));
  if (callout.href) {
    const link = el("a", null, callout.link || "Source");
    link.href = callout.href;
    block.append(link);
  }
  return block;
}

function render(page) {
  const app = document.querySelector("#app");
  app.replaceChildren();
  if (page.status) app.append(badge(page.status));
  app.append(el("h1", null, page.title), el("p", "summary", page.summary));
  [renderStats(page.stats), renderCards(page.cards)]
    .filter(Boolean)
    .forEach((node) => app.append(node));
  (page.charts || []).forEach((chart) => app.append(renderChart(chart)));
  [renderTable(page.table), renderCallout(page.callout)].filter(Boolean).forEach((node) => app.append(node));
  if (page.sources) {
    const list = el("ul", "sources");
    page.sources.forEach((source) => list.append(el("li", null, source)));
    app.append(list);
  }
}

fetch(`data/${pageId}.json`)
  .then((response) => {
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  })
  .then(render)
  .catch(() => {
    document.querySelector("#app").textContent =
      "The figures could not be loaded. Serve this folder over http, for example python -m http.server in docs/.";
  });
