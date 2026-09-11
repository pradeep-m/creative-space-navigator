const state = {
  runId: null,
  ideas: [],
  ideasById: {},
  themes: [],
  maps: [],
  placements: {},   // map_id -> [{idea_id, x, y}]
  selections: {},   // map_id -> {x_side, y_side}
};

const $ = (id) => document.getElementById(id);
const themesEl = $('themes');
const mapsEl = $('maps');
const statusEl = $('status');
const selbar = $('selbar');

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function setStatus(text, { busy = false, error = false } = {}) {
  statusEl.hidden = !text;
  statusEl.className = error ? 'status error' : 'status';
  statusEl.replaceChildren();
  if (busy) statusEl.appendChild(el('span', 'spinner'));
  if (text) statusEl.appendChild(document.createTextNode(text));
}

async function api(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${path} failed (${res.status})`);
  return data;
}

function ideaCard(idea, cls) {
  const wrap = el('div', cls || 'idea');
  wrap.appendChild(el('div', 'hl', idea.headline));
  wrap.appendChild(el('div', 'bd', idea.body));
  if (idea.angle) wrap.appendChild(el('div', 'ang', idea.angle));
  return wrap;
}

/* ---------------- version 1: themes ---------------- */

function renderThemes() {
  themesEl.replaceChildren();

  state.themes.forEach((theme) => {
    const card = el('div', 'theme');

    const top = el('div', 'theme-top');
    top.appendChild(el('h3', null, theme.name));
    top.appendChild(el('span', 'count', `${theme.idea_ids.length} concepts`));
    card.appendChild(top);
    card.appendChild(el('p', 'desc', theme.description));

    theme.idea_ids
      .map((id) => state.ideasById[id])
      .filter(Boolean)
      .slice(0, 3)
      .forEach((idea) => card.appendChild(ideaCard(idea)));

    if (theme.idea_ids.length > 3) {
      card.appendChild(el('div', 'cell-more', `+ ${theme.idea_ids.length - 3} more in this theme`));
    }

    const wrap = el('div', 'more-wrap');
    const btn = el('button', 'more-btn', 'Generate more in this direction');
    btn.onclick = () => expandTheme(theme, card, btn);
    wrap.appendChild(btn);
    card.appendChild(wrap);

    themesEl.appendChild(card);
  });
}

async function expandTheme(theme, card, btn) {
  btn.disabled = true;
  btn.textContent = 'Generating…';
  try {
    const data = await api('/api/refine/theme', { run_id: state.runId, theme_id: theme.id });
    const block = el('div', 'new-block');
    block.appendChild(el('div', 'label', `New concepts in "${theme.name}"`));
    data.ideas.forEach((idea) => block.appendChild(ideaCard(idea)));
    card.insertBefore(block, btn.parentElement);
    btn.textContent = 'Generate more in this direction';
  } catch (err) {
    btn.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
}

/* ---------------- version 2: 2x2 maps ---------------- */

const sideOf = (v) => (v >= 0 ? 'high' : 'low');
const labelFor = (axis, side) => (side === 'high' ? axis.high_label : axis.low_label);

function ideasInQuadrant(mapId, xSide, ySide) {
  const points = state.placements[mapId] || [];
  return points
    .filter((p) => sideOf(p.x) === xSide && sideOf(p.y) === ySide)
    .sort((a, b) => Math.abs(b.x) + Math.abs(b.y) - (Math.abs(a.x) + Math.abs(a.y)))
    .map((p) => state.ideasById[p.idea_id])
    .filter(Boolean);
}

function renderMaps() {
  mapsEl.replaceChildren();

  state.maps.forEach((m) => {
    const card = el('div', 'map');
    card.appendChild(el('h3', null, m.title));
    card.appendChild(el('p', 'rationale', m.rationale));

    const plot = el('div', 'plot');
    plot.appendChild(el('div', 'axis-label ax-yhigh', `▲ ${m.y_axis.high_label}`));
    plot.appendChild(el('div', 'axis-label ax-ylow', `▼ ${m.y_axis.low_label}`));
    plot.appendChild(el('div', 'axis-label ax-xlow', `◀ ${m.x_axis.low_label}`));
    plot.appendChild(el('div', 'axis-label ax-xhigh', `${m.x_axis.high_label} ▶`));

    const cells = el('div', 'cells');
    // Top row is the +1 pole of the y axis, so it reads like a normal chart.
    [['low', 'high'], ['high', 'high'], ['low', 'low'], ['high', 'low']].forEach(
      ([xSide, ySide]) => cells.appendChild(buildCell(m, xSide, ySide))
    );
    plot.appendChild(cells);

    card.appendChild(plot);
    mapsEl.appendChild(card);
  });
}

function buildCell(m, xSide, ySide) {
  const ideas = state.placements[m.id] ? ideasInQuadrant(m.id, xSide, ySide) : null;
  const sel = state.selections[m.id];
  const isSelected = sel && sel.x_side === xSide && sel.y_side === ySide;

  const cell = el('button', 'cell');
  cell.type = 'button';
  cell.dataset.mapId = m.id;
  cell.dataset.xSide = xSide;
  cell.dataset.ySide = ySide;

  const head = el('div', 'cell-head');
  head.appendChild(
    el('div', 'cell-name', `${labelFor(m.x_axis, xSide)} · ${labelFor(m.y_axis, ySide)}`)
  );
  if (ideas) head.appendChild(el('div', 'cell-count', String(ideas.length)));
  cell.appendChild(head);

  const list = el('div', 'cell-list');
  if (ideas === null) {
    list.appendChild(el('div', 'cell-item', 'Waiting for concepts…'));
  } else if (ideas.length === 0) {
    list.appendChild(el('div', 'cell-item', 'No concepts landed here.'));
  } else {
    ideas.slice(0, 3).forEach((idea) => list.appendChild(el('div', 'cell-item', idea.headline)));
    if (ideas.length > 3) list.appendChild(el('div', 'cell-more', `+ ${ideas.length - 3} more`));
  }
  cell.appendChild(list);

  if (isSelected) cell.classList.add('selected');
  if (ideas === null) {
    cell.classList.add('dead');
    cell.disabled = true;
  } else {
    cell.onclick = () => toggleQuadrant(m.id, xSide, ySide);
  }
  return cell;
}

function toggleQuadrant(mapId, xSide, ySide) {
  const current = state.selections[mapId];
  if (current && current.x_side === xSide && current.y_side === ySide) {
    delete state.selections[mapId];
  } else {
    state.selections[mapId] = { x_side: xSide, y_side: ySide };
  }
  refreshSelectionStyles();
  renderSelbar();
}

function refreshSelectionStyles() {
  mapsEl.querySelectorAll('.cell').forEach((cell) => {
    const sel = state.selections[cell.dataset.mapId];
    const on = sel && sel.x_side === cell.dataset.xSide && sel.y_side === cell.dataset.ySide;
    cell.classList.toggle('selected', Boolean(on));
  });
}

function selectionLabel() {
  const parts = [];
  state.maps.forEach((m) => {
    const sel = state.selections[m.id];
    if (!sel) return;
    parts.push(labelFor(m.x_axis, sel.x_side), labelFor(m.y_axis, sel.y_side));
  });
  return parts.join(' × ');
}

function renderSelbar() {
  const count = Object.keys(state.selections).length;
  selbar.hidden = count === 0;
  if (count === 0) return;

  $('sel-label').textContent = selectionLabel();
  const btn = $('gen-intersection');
  btn.textContent =
    count < state.maps.length
      ? `Generate concepts here (${count}/${state.maps.length} maps)`
      : 'Generate concepts here';
}

async function generateIntersection() {
  const btn = $('gen-intersection');
  const panel = $('intersection');
  const selections = Object.entries(state.selections).map(([map_id, sides]) => ({
    map_id,
    ...sides,
  }));

  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = 'Generating…';
  panel.hidden = false;
  panel.replaceChildren(el('p', 'empty', 'Generating concepts for this intersection…'));

  try {
    const data = await api('/api/refine/intersection', {
      run_id: state.runId,
      selections,
    });
    panel.replaceChildren();
    panel.appendChild(el('h3', null, 'Concepts at this intersection'));
    panel.appendChild(el('p', 'combo', data.label));
    if (data.tension_note) panel.appendChild(el('div', 'tension', data.tension_note));
    data.ideas.forEach((idea) => panel.appendChild(ideaCard(idea)));
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (err) {
    panel.replaceChildren(el('p', 'empty', err.message));
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

/* ---------------- orchestration ---------------- */

async function explore(product, audience) {
  const go = $('go');
  go.disabled = true;
  Object.assign(state, {
    runId: null, ideas: [], ideasById: {}, themes: [], maps: [],
    placements: {}, selections: {},
  });
  themesEl.replaceChildren(el('p', 'empty', 'Waiting for concepts…'));
  mapsEl.replaceChildren(el('p', 'empty', 'Proposing creative dimensions…'));
  $('intersection').hidden = true;
  renderSelbar();

  try {
    setStatus('Proposing mostly-orthogonal creative dimensions…', { busy: true });
    const dims = await api('/api/dimensions', { product, audience });
    state.runId = dims.run_id;
    state.maps = dims.maps;
    renderMaps();  // axes now visible; cells fill in once placement lands

    setStatus('Generating a diverse concept corpus that spans those dimensions…', { busy: true });
    const corpus = await api('/api/corpus', { run_id: state.runId });
    state.ideas = corpus.ideas;
    state.ideasById = Object.fromEntries(corpus.ideas.map((i) => [i.id, i]));

    setStatus('Grouping into themes and projecting onto the maps…', { busy: true });
    const [themesRes, mapsRes] = await Promise.allSettled([
      api('/api/themes', { run_id: state.runId }).then((d) => {
        state.themes = d.themes;
        renderThemes();
      }),
      api('/api/maps', { run_id: state.runId }).then((d) => {
        d.maps.forEach((m) => { state.placements[m.map_id] = m.placements; });
        renderMaps();
      }),
    ]);

    const failures = [themesRes, mapsRes].filter((r) => r.status === 'rejected');
    if (failures.length) {
      setStatus(failures.map((f) => f.reason.message).join(' · '), { error: true });
    } else {
      setStatus(
        `${state.ideas.length} concepts · ${state.themes.length} themes · ${state.maps.length} maps. ` +
        `Pick one quadrant per map to compose a direction.`
      );
    }
    if (themesRes.status === 'rejected') {
      themesEl.replaceChildren(el('p', 'empty', themesRes.reason.message));
    }
  } catch (err) {
    setStatus(err.message, { error: true });
    mapsEl.replaceChildren(el('p', 'empty', 'Could not build the maps.'));
    themesEl.replaceChildren(el('p', 'empty', 'Could not build the themes.'));
  } finally {
    go.disabled = false;
  }
}

$('brief').addEventListener('submit', (e) => {
  e.preventDefault();
  explore($('product').value.trim(), $('audience').value.trim());
});

$('gen-intersection').addEventListener('click', generateIntersection);

$('clear-sel').addEventListener('click', () => {
  state.selections = {};
  refreshSelectionStyles();
  renderSelbar();
});

fetch('/api/config')
  .then((r) => r.json())
  .then((cfg) => {
    if (cfg.mock) {
      document.querySelector('.titles h1').appendChild(el('span', 'mock-flag', 'MOCK'));
    }
  })
  .catch(() => {});
