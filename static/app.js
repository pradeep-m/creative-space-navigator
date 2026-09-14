// The server is stateless, so this object is the single source of truth for a run and
// the relevant slices get posted back with every request.
const state = {
  product: '',
  audience: '',
  ideas: [],
  ideasById: {},
  themes: [],
  maps: [],
  placements: {},   // map_id -> [{idea_id, x, y}]
  selections: {},   // map_id -> {x_side, y_side}
  batches: [],      // generated intersection rounds, newest last
};

const brief = () => ({ product: state.product, audience: state.audience });

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

const VISIBLE = 3;  // how many examples a card or quadrant shows before collapsing

function overflowToggle(hiddenNodes, label) {
  const btn = el('button', 'more-toggle', label(hiddenNodes.length));
  btn.type = 'button';
  btn.onclick = (event) => {
    // Quadrants are themselves clickable, so don't let this bubble into a selection.
    event.stopPropagation();
    const opening = hiddenNodes[0].hidden;
    hiddenNodes.forEach((node) => { node.hidden = !opening; });
    btn.textContent = opening ? 'Show fewer' : label(hiddenNodes.length);
  };
  return btn;
}

// Native <details> so the browser supplies keyboard handling, disclosure semantics
// and open/close state. Collapsed by default to keep the panes scannable.
function disclosure(title, body, trailing) {
  const wrap = el('details', 'blurb');
  const summary = document.createElement('summary');
  summary.appendChild(el('span', 'chev', '▸'));
  summary.appendChild(el('h3', null, title));
  if (trailing) summary.appendChild(trailing);
  wrap.appendChild(summary);
  if (body) wrap.appendChild(el('p', 'blurb-body', body));
  return wrap;
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

    card.appendChild(
      disclosure(
        theme.name,
        theme.description,
        el('span', 'count', `${theme.idea_ids.length} concepts`)
      )
    );

    const themeIdeas = theme.idea_ids.map((id) => state.ideasById[id]).filter(Boolean);
    const nodes = themeIdeas.map((idea, i) => {
      const node = ideaCard(idea);
      if (i >= VISIBLE) node.hidden = true;
      card.appendChild(node);
      return node;
    });

    if (themeIdeas.length > VISIBLE) {
      card.appendChild(
        overflowToggle(nodes.slice(VISIBLE), (n) => `+ ${n} more in this theme`)
      );
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
    const data = await api('/api/refine/theme', {
      ...brief(),
      theme,
      examples: theme.idea_ids.map((id) => state.ideasById[id]).filter(Boolean),
    });
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
    card.appendChild(disclosure(m.title, m.rationale));

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

  // A div rather than a button, because the overflow toggle nests inside it and
  // interactive content cannot live inside a <button>.
  const cell = el('div', 'cell');
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
    const nodes = ideas.map((idea, i) => {
      const node = el('div', 'cell-item', idea.headline);
      if (i >= VISIBLE) node.hidden = true;
      list.appendChild(node);
      return node;
    });
    if (ideas.length > VISIBLE) {
      list.appendChild(overflowToggle(nodes.slice(VISIBLE), (n) => `+ ${n} more`));
    }
  }
  cell.appendChild(list);

  if (isSelected) cell.classList.add('selected');
  if (ideas === null) {
    cell.classList.add('dead');
  } else {
    const toggle = () => toggleQuadrant(m.id, xSide, ySide);
    cell.setAttribute('role', 'button');
    cell.tabIndex = 0;
    cell.setAttribute('aria-pressed', String(Boolean(isSelected)));
    cell.onclick = toggle;
    cell.onkeydown = (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggle();
      }
    };
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
    if (cell.hasAttribute('role')) cell.setAttribute('aria-pressed', String(Boolean(on)));
  });
}

function snapshotSelections() {
  return Object.fromEntries(
    Object.entries(state.selections).map(([id, sides]) => [id, { ...sides }])
  );
}

function selectionKey(selections) {
  return state.maps
    .map((m) => {
      const sel = selections[m.id];
      return sel ? `${m.id}:${sel.x_side}:${sel.y_side}` : '';
    })
    .filter(Boolean)
    .join('|');
}

function selectedQuadrants(selections) {
  return state.maps.flatMap((m) => {
    const sel = selections[m.id];
    if (!sel) return [];
    return [{
      mapTitle: m.title,
      quadrant: `${labelFor(m.x_axis, sel.x_side)} · ${labelFor(m.y_axis, sel.y_side)}`,
    }];
  });
}

function selectionLabel(selections = state.selections) {
  return selectedQuadrants(selections)
    .map((q) => q.quadrant)
    .join(' × ');
}

function renderSelbar() {
  const count = Object.keys(state.selections).length;
  selbar.hidden = count === 0;
  if (count === 0) return;

  $('sel-label').textContent = selectionLabel();
  const btn = $('gen-intersection');
  if (btn.disabled) return;

  const key = selectionKey(state.selections);
  const already = state.batches.some((b) => b.key === key && !b.pending && b.ideas.length);
  const verb = already ? 'Generate more here' : 'Generate concepts here';
  btn.textContent =
    count < state.maps.length ? `${verb} (${count}/${state.maps.length} maps)` : verb;
}

function renderIntersection() {
  const panel = $('intersection');
  if (state.batches.length === 0) {
    panel.hidden = true;
    panel.replaceChildren();
    return;
  }

  panel.hidden = false;
  panel.replaceChildren();
  panel.appendChild(el('h3', null, 'Generated concepts'));

  state.batches.forEach((batch, i) => {
    const block = el('div', 'gen-batch');
    if (batch.pending) block.classList.add('pending');

    const head = el('div', 'gen-batch-head');
    head.appendChild(el('div', 'gen-batch-title', `Round ${i + 1}`));
    const chips = el('div', 'quad-chips');
    batch.quadrants.forEach((q) => {
      const chip = el('span', 'quad-chip');
      chip.appendChild(el('span', 'quad-chip-map', q.mapTitle));
      chip.appendChild(el('span', 'quad-chip-name', q.quadrant));
      chips.appendChild(chip);
    });
    head.appendChild(chips);
    block.appendChild(head);

    if (batch.pending) {
      const wait = el('p', 'empty');
      wait.appendChild(el('span', 'spinner'));
      wait.appendChild(document.createTextNode('Generating concepts for this selection…'));
      block.appendChild(wait);
    } else if (batch.error) {
      block.appendChild(el('p', 'empty', batch.error));
    } else {
      if (batch.tension_note) block.appendChild(el('div', 'tension', batch.tension_note));
      batch.ideas.forEach((idea) => block.appendChild(ideaCard(idea)));
    }
    panel.appendChild(block);
  });

  const more = el('button', 'more-btn', 'Generate more with the selected quadrants');
  more.type = 'button';
  more.disabled = $('gen-intersection').disabled || Object.keys(state.selections).length === 0;
  more.onclick = generateIntersection;
  panel.appendChild(more);
}

async function generateIntersection() {
  const btn = $('gen-intersection');
  if (btn.disabled || Object.keys(state.selections).length === 0) return;

  const selections = snapshotSelections();
  const payload = Object.entries(selections).map(([map_id, sides]) => ({ map_id, ...sides }));
  const key = selectionKey(selections);
  const prior_headlines = state.batches
    .filter((b) => b.key === key && !b.pending)
    .flatMap((b) => b.ideas.map((idea) => idea.headline).filter(Boolean));

  const batch = {
    key,
    selections,
    quadrants: selectedQuadrants(selections),
    pending: true,
    ideas: [],
    tension_note: '',
    error: null,
  };
  state.batches.push(batch);

  btn.disabled = true;
  btn.textContent = 'Generating…';
  renderIntersection();
  $('intersection').querySelector('.gen-batch.pending')
    ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  try {
    const data = await api('/api/refine/intersection', {
      ...brief(),
      maps: state.maps,
      selections: payload,
      prior_headlines,
    });
    batch.pending = false;
    batch.ideas = data.ideas || [];
    batch.tension_note = data.tension_note || '';
  } catch (err) {
    batch.pending = false;
    batch.error = err.message;
  } finally {
    btn.disabled = false;
    renderSelbar();
    renderIntersection();
    const batches = $('intersection').querySelectorAll('.gen-batch');
    batches[batches.length - 1]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

/* ---------------- orchestration ---------------- */

async function explore(product, audience) {
  const go = $('go');
  go.disabled = true;
  Object.assign(state, {
    product, audience, ideas: [], ideasById: {}, themes: [], maps: [],
    placements: {}, selections: {}, batches: [],
  });
  themesEl.replaceChildren(el('p', 'empty', 'Waiting for concepts…'));
  mapsEl.replaceChildren(el('p', 'empty', 'Proposing creative dimensions…'));
  $('intersection').hidden = true;
  renderSelbar();

  try {
    setStatus('Proposing mostly-orthogonal creative dimensions…', { busy: true });
    const dims = await api('/api/dimensions', brief());
    state.maps = dims.maps;
    renderMaps();  // axes now visible; cells fill in once placement lands

    setStatus('Generating a diverse concept corpus that spans those dimensions…', { busy: true });
    const corpus = await api('/api/corpus', { ...brief(), maps: state.maps });
    state.ideas = corpus.ideas;
    state.ideasById = Object.fromEntries(corpus.ideas.map((i) => [i.id, i]));

    setStatus('Grouping into themes and projecting onto the maps…', { busy: true });
    const [themesRes, mapsRes] = await Promise.allSettled([
      api('/api/themes', { ...brief(), ideas: state.ideas }).then((d) => {
        state.themes = d.themes;
        renderThemes();
      }),
      api('/api/maps', { ...brief(), ideas: state.ideas, maps: state.maps }).then((d) => {
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
