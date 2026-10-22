/* Layercast card: shows a person dressed for the periods of your day, using the
 * recommendations of the Layercast period sensors.
 * Plain JavaScript, no build step. Registered automatically by the integration. */

const STATIC = "/layercast_static";
const ICONS = `${STATIC}/icons/`;

/* Built-in figures: name -> folder with a figure.json. To add one, put a folder next to
 * figures/neutral and list it here. Users can also point `figure_url` at their own folder. */
const FIGURES = {
  neutral: `${STATIC}/figures/neutral/`,
};

const TEXT = {
  en: {
    feels: "feels",
    later: "Later:",
    tomorrow: "Tomorrow",
    noData: "No forecast for this period yet",
    unsupported: (n) => `${n} rule(s) cannot be evaluated`,
    unsupportedHint: "The weather source does not provide the data these rules need:",
    missing: (id) => `Entity not found: ${id}`,
    nothing: "Nothing special needed",
    figureFailed: (url) => `Figure could not be loaded: ${url}`,
    title: "Title",
    entities: "Periods",
    layout: "Layout",
    figure: "Figure",
    figure_url: "Own figure folder (URL, overrides figure)",
    show_weather: "Show weather values",
    show_warnings: "Show warnings about rules that cannot be evaluated",
    layoutHelp:
      "Auto picks the view from the width of the card: compact when narrow, a small timeline when medium, the timeline when wide. Compact shows only the period that is running now, or the next one.",
  },
  de: {
    feels: "gefühlt",
    later: "Später:",
    tomorrow: "morgen",
    noData: "Noch keine Vorhersage für diesen Zeitraum",
    unsupported: (n) => `${n} Regel(n) nicht auswertbar`,
    unsupportedHint: "Die Wetterquelle liefert die Daten nicht, die diese Regeln brauchen:",
    missing: (id) => `Entität nicht gefunden: ${id}`,
    nothing: "Nichts Besonderes nötig",
    figureFailed: (url) => `Figur konnte nicht geladen werden: ${url}`,
    title: "Titel",
    entities: "Zeiträume",
    layout: "Darstellung",
    figure: "Figur",
    figure_url: "Eigener Figurenordner (URL, ersetzt Figur)",
    show_weather: "Wetterwerte anzeigen",
    show_warnings: "Warnungen zu nicht auswertbaren Regeln anzeigen",
    layoutHelp:
      "Auto wählt die Darstellung nach der Breite der Karte: kompakt, wenn sie schmal ist, eine kleine Zeitleiste bei mittlerer Breite, sonst die Zeitleiste. Kompakt zeigt nur den Zeitraum, der gerade läuft, oder den nächsten.",
  },
};

const DROP = "M12 2C12 2 5 10 5 15a7 7 0 0 0 14 0C19 10 12 2 12 2z";
const WARNING = "M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z";

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const icon = (path) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;

/* The language of the UI, for the card editor (which gets no hass object). */
const uiLanguage = () =>
  (typeof document !== "undefined" && document.documentElement?.lang) ||
  (typeof navigator !== "undefined" && navigator.language) ||
  "en";

/* A figure is a folder with a figure.json: the canvas size, a body image and one
 * transparent layer per garment, all drawn on the same canvas so they line up:
 *   { "name": "...", "width": 160, "height": 320, "base": "body.svg",
 *     "layers": { "<image key>": { "file": "jacket.svg", "z": 40 } } }
 * Layers can be SVG or PNG. Loaded once per folder. */
const figureCache = new Map();

function loadFigure(base) {
  if (!figureCache.has(base)) {
    figureCache.set(
      base,
      fetch(`${base}figure.json`)
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        })
        .then((data) => {
          if (!data.base || !data.width || !data.height || typeof data.layers !== "object") {
            throw new Error("figure.json needs width, height, base and layers");
          }
          return { ...data, url: base };
        })
        .catch((error) => {
          console.warn(`layercast-card: cannot load figure ${base}`, error);
          figureCache.delete(base); // allow a retry on the next render
          return null;
        }),
    );
  }
  return figureCache.get(base);
}

/* Items the figure draws are stacked as layers; everything else (a rule with its own image
 * URL, a garment this figure has no layer for, sunscreen, ...) becomes a small badge. */
function badgeHtml(item) {
  const src = item.image_url || `${ICONS}${item.image}.svg`;
  return `<span class="badge" tabindex="0" data-name="${esc(item.name)}" aria-label="${esc(item.name)}" role="img">
    <img src="${esc(src)}" data-fallback="${ICONS}generic.svg" alt="">
  </span>`;
}

function figureParts(items, ctx) {
  const { figure } = ctx;
  if (figure === undefined) return { figure: "", badges: "" }; // still loading
  const drawn = [];
  const badges = [];
  for (const item of items) {
    (figure?.layers?.[item.image] && !item.image_url ? drawn : badges).push(item);
  }
  const names = items.map((item) => item.name).join(", ");

  let figureHtml = "";
  if (figure) {
    const layers = drawn
      .map((item) => ({ ...figure.layers[item.image], name: item.name }))
      .sort((a, b) => (a.z ?? 0) - (b.z ?? 0))
      .map((layer) => `<img src="${esc(figure.url + layer.file)}" alt="" style="z-index:${Number(layer.z) || 0}">`)
      .join("");
    figureHtml = `<div class="figure" role="img" aria-label="${esc(names)}" style="aspect-ratio:${Number(figure.width)}/${Number(figure.height)}">
      <img src="${esc(figure.url + figure.base)}" alt="">${layers}
    </div>`;
  }
  return {
    figure: figureHtml,
    badges: badges.length ? `<div class="badges">${badges.map(badgeHtml).join("")}</div>` : "",
  };
}

/* What a column of the card shows, worked out once and shared by the layouts. */
function prepare({ id, attrs, state }, ctx) {
  const { t } = ctx;
  const values = attrs.values || {};
  const hasData = state !== "unknown" && state !== "unavailable" && attrs.hours > 0;
  const items = attrs.items || [];

  const temp = hasData ? ctx.range(values.temp_min, values.temp_max) : "";
  const tempShort = hasData ? ctx.range(values.temp_min, values.temp_max, true) : "";
  const feelsDiffers =
    values.feels_min != null &&
    values.feels_max != null &&
    (ctx.num(values.feels_min) !== ctx.num(values.temp_min) ||
      ctx.num(values.feels_max) !== ctx.num(values.temp_max));

  // The detail line: feels-like, rain and UV, each only if there is something to say.
  const parts = [];
  if (hasData) {
    if (feelsDiffers) {
      parts.push({ cls: "feels", text: `${t.feels} ${ctx.range(values.feels_min, values.feels_max, true)}` });
    }
    // Some sources (dwd_weather with hourly updates) have no rain probability: show the amount.
    const rain = values.rain_probability_max != null ? `${Math.round(values.rain_probability_max)}%` : ctx.amount(values.rain_sum);
    if (rain) parts.push({ cls: "rain", text: rain, drop: true });
    if (values.uv_max > 0) parts.push({ cls: "uv", text: `UV ${Math.round(values.uv_max)}` });
  }
  const detail = {
    text: parts.map((p) => p.text).join(" · "),
    html: parts
      .map((p) => `<span class="${p.cls}">${p.drop ? icon(DROP) : ""}${esc(p.text)}</span>`)
      .join(`<span class="sep">·</span>`),
  };

  const names = items.map((item) => item.name).join(", ");
  return {
    id,
    attrs,
    name: attrs.period,
    hasData,
    items,
    temp,
    tempShort,
    detail,
    unsupported: attrs.unsupported || [],
    label: `${attrs.period}: ${hasData ? names || t.nothing : t.noData}`,
    timeRange: `${ctx.time(attrs.start)} – ${ctx.time(attrs.end, false)}`,
  };
}

function warning(column, ctx, iconOnly) {
  if (!ctx.showWarnings || !column.unsupported.length) return "";
  const hint = `${ctx.t.unsupportedHint} ${column.unsupported.join(", ")}`;
  return iconOnly
    ? `<span class="warn icon" title="${esc(hint)}" aria-label="${esc(hint)}" role="img">${icon(WARNING)}</span>`
    : `<div class="warn" title="${esc(hint)}">${icon(WARNING)}${esc(ctx.t.unsupported(column.unsupported.length))}</div>`;
}

const byStart = (a, b) => String(a.attrs.start).localeCompare(String(b.attrs.start));

const open = (column, extra = "") =>
  `data-entity="${esc(column.id)}" tabindex="0" role="button" aria-label="${esc(column.label)}"${extra}`;

/* Layouts: add an entry here and it shows up in the card editor. `render` gets the period
 * sensors' states and returns HTML; `grid` is the default size in the sections view and
 * `size(n)` the height in the masonry view (units of 50 px) for n periods. */
const LAYOUTS = {
  timeline: {
    label: "Timeline",
    render: (periods, ctx) => timeline(periods, ctx, false),
    grid: { columns: 12, min_columns: 6 },
    size: () => 7,
  },
  "timeline-small": {
    label: "Timeline (small)",
    render: (periods, ctx) => timeline(periods, ctx, true),
    grid: { columns: 12, min_columns: 3 },
    size: () => 5,
  },
  compact: {
    label: "Compact",
    render: compact,
    grid: { columns: 6, min_columns: 3 },
    size: () => 4,
  },
  list: {
    label: "List",
    render: list,
    grid: { columns: 6, min_columns: 3 },
    size: (n) => n + 1,
  },
};

/* "auto" picks one of these by the width of the card (px). Not the list: it has no figure. */
const AUTO_LAYOUTS = ["compact", "timeline-small", "timeline"];
const AUTO_LIMITS = [320, 520];
const AUTO_HYSTERESIS = 20;

/* The index into AUTO_LAYOUTS for a width. Close to a limit, the previous one is kept, so a card
 * that is resized by a few pixels does not flip back and forth. */
function autoLevel(width, previous) {
  let level = AUTO_LIMITS.filter((limit) => width >= limit).length;
  if (previous !== undefined && previous !== level) {
    const limit = AUTO_LIMITS[Math.min(level, previous)];
    if (Math.abs(width - limit) < AUTO_HYSTERESIS) level = previous;
  }
  return level;
}

/* A column per period. A row (temperature, detail line) only exists if at least one column has
 * something for it, and then in all columns, so the figures start at the same height. */
function timeline(periods, ctx, small) {
  const columns = [...periods].sort(byStart).map((p) => prepare(p, ctx));
  const rows = {
    time: !small,
    temp: ctx.showWeather && columns.some((c) => c.temp),
    detail: ctx.showWeather && !small && columns.some((c) => c.detail.text),
  };
  return `<div class="timeline${small ? " small" : ""}">${columns
    .map((c) => timelineColumn(c, rows, ctx, small))
    .join("")}</div>`;
}

function timelineColumn(c, rows, ctx, small) {
  const { t } = ctx;
  let body;
  if (!c.hasData) body = `<p class="muted">${esc(t.noData)}</p>`;
  else if (!c.items.length) body = `<p class="muted">${esc(t.nothing)}</p>`;
  else {
    const parts = figureParts(c.items, ctx);
    body = parts.figure + parts.badges;
  }
  return `<section ${open(c, ` title="${esc(`${c.name} ${c.timeRange}`)}"`)}>
    <h3 class="row name">${esc(c.name)}</h3>
    ${rows.time ? `<div class="row muted time">${esc(c.timeRange)}</div>` : ""}
    ${rows.temp ? `<div class="row temp">${esc(small ? c.tempShort : c.temp)}</div>` : ""}
    ${rows.detail ? `<div class="row muted detail" title="${esc(c.detail.text)}">${c.detail.html}</div>` : ""}
    <div class="body">${body}</div>
    ${warning(c, ctx, small)}
  </section>`;
}

/* The period that is running now, or else the next one. If several run, the one that started last. */
function pickPeriod(periods, now) {
  const timed = periods
    .map((p) => ({ p, start: Date.parse(p.attrs.start), end: Date.parse(p.attrs.end) }))
    .filter((x) => !Number.isNaN(x.start) && !Number.isNaN(x.end));
  const running = timed.filter((x) => x.start <= now && now < x.end).sort((a, b) => b.start - a.start)[0];
  const next = timed.filter((x) => x.start > now).sort((a, b) => a.start - b.start)[0];
  return (running || next || timed[0] || { p: periods[0] }).p;
}

/* Items of the later periods of that day that the chosen period does not have: the umbrella
 * that is only needed this evening. */
function laterItems(chosen, periods, ctx) {
  const start = Date.parse(chosen.attrs.start);
  const day = ctx.ymd(new Date(start));
  const have = new Set((chosen.attrs.items || []).map((item) => item.name));
  const names = [];
  for (const p of [...periods].sort(byStart)) {
    const pStart = Date.parse(p.attrs.start);
    if (p === chosen || !(pStart > start) || ctx.ymd(new Date(pStart)) !== day || !(p.attrs.hours > 0)) continue;
    for (const item of p.attrs.items || []) {
      if (!have.has(item.name) && !names.includes(item.name)) names.push(item.name);
    }
  }
  return names;
}

function compact(periods, ctx) {
  const { t } = ctx;
  const chosen = pickPeriod(periods, ctx.now().getTime());
  const c = prepare(chosen, ctx);
  const later = laterItems(chosen, periods, ctx);

  let figure = "";
  let badges = "";
  let message = "";
  if (!c.hasData) message = `<p class="muted">${esc(t.noData)}</p>`;
  else if (!c.items.length) message = `<p class="muted">${esc(t.nothing)}</p>`;
  else ({ figure, badges } = figureParts(c.items, ctx));

  const shown = later.slice(0, 3).join(", ") + (later.length > 3 ? ", …" : "");
  return `<div class="compact">
    <section ${open(c)}>
      <div class="c-fig">${figure}</div>
      <div class="c-text">
        <h3 class="row name">${esc(c.name)}</h3>
        <div class="row muted time">${esc(c.timeRange)}</div>
        ${ctx.showWeather && c.temp ? `<div class="row temp">${esc(c.temp)}</div>` : ""}
        ${ctx.showWeather && c.detail.text ? `<div class="row muted detail" title="${esc(c.detail.text)}">${c.detail.html}</div>` : ""}
        ${later.length ? `<div class="later" title="${esc(later.join(", "))}">${esc(t.later)} + ${esc(shown)}</div>` : ""}
        ${message}${badges}${warning(c, ctx, true)}
      </div>
    </section>
  </div>`;
}

function list(periods, ctx) {
  const { t } = ctx;
  const columns = [...periods].sort(byStart).map((p) => prepare(p, ctx));
  const showTemp = ctx.showWeather && columns.some((c) => c.temp);
  const grid = showTemp ? "minmax(0,10em) 5em minmax(0,1fr) 18px" : "minmax(0,10em) minmax(0,1fr) 18px";
  const rows = columns.map((c) => {
    let icons;
    if (!c.hasData) icons = `<span class="muted">${esc(t.noData)}</span>`;
    else if (!c.items.length) icons = `<span class="muted">${esc(t.nothing)}</span>`;
    else icons = c.items.map(badgeHtml).join("");
    return `<div class="l-row" ${open(c)}>
      <div class="l-name"><div class="row name">${esc(c.name)}</div><div class="row muted time">${esc(c.timeRange)}</div></div>
      ${showTemp ? `<div class="l-temp">${esc(c.tempShort)}</div>` : ""}
      <div class="l-icons">${icons}</div>
      ${warning(c, ctx, true) || "<span></span>"}
    </div>`;
  });
  return `<div class="list" style="--cols:${grid}">${rows.join("")}</div>`;
}

const STYLE = `
  :host { display: block; }
  .row { min-height: 1.4em; line-height: 1.4em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  h3 { margin: 0; font-size: 1.1em; font-weight: 500; color: var(--primary-text-color); }
  .muted { color: var(--secondary-text-color); font-size: 0.85em; }
  .temp { margin-top: 4px; font-size: 1.3em; line-height: 1.4em; color: var(--primary-text-color); }
  .detail svg, .warn svg { width: 13px; height: 13px; fill: currentColor; flex: none; }
  .detail svg { vertical-align: -2px; margin-right: 2px; }
  .sep { margin: 0 4px; opacity: 0.6; }
  .rain { color: var(--info-color, #1e88e5); }
  .uv { color: var(--warning-color, #ffa600); }
  [data-entity] { cursor: pointer; }
  [data-entity]:focus-visible { outline: 2px solid var(--primary-color, #03a9f4); outline-offset: -2px; border-radius: 8px; }
  .figure { position: relative; height: var(--fig); margin: 12px auto 0; }
  .figure img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
  .badges { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin-top: 8px; }
  .badge { position: relative; width: 32px; height: 32px; border-radius: 50%; outline: none;
           background: var(--secondary-background-color, #f4f4f4); display: grid; place-items: center; }
  .badge img { width: 22px; height: 22px; }
  .badge:hover::after, .badge:focus::after {
    content: attr(data-name); position: absolute; bottom: calc(100% + 4px); left: 50%;
    transform: translateX(-50%); z-index: 100; white-space: nowrap; padding: 2px 8px;
    border-radius: 4px; font-size: 0.75em; color: var(--card-background-color, #fff);
    background: var(--primary-text-color, #212121); }
  .warn { margin-top: 8px; display: flex; gap: 4px; align-items: center; justify-content: center;
          font-size: 0.75em; color: var(--warning-color, #ffa600); }
  .warn.icon { margin: 0; display: inline-flex; }
  .warn.icon svg { width: 16px; height: 16px; }
  .error { padding: 16px; color: var(--error-color, #db4437); }

  .timeline { --fig: 200px; display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .timeline.small { --fig: 140px; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); }
  .timeline section { padding: 12px 16px; text-align: center; border-left: 1px solid var(--divider-color); }
  .timeline.small section { padding: 8px; }
  .timeline.small .temp { font-size: 1.15em; }
  .timeline section:first-child { border-left: none; }
  .timeline .warn.icon { display: flex; justify-content: center; margin-top: 8px; }
  .body { min-height: calc(var(--fig) + 12px); }
  .body > p { margin: 12px 0 0; }

  .compact { --fig: 150px; container-type: inline-size; }
  .compact section { display: flex; gap: 12px; align-items: center; padding: 12px 16px; text-align: left; }
  .compact .c-fig { flex: none; }
  .compact .figure { margin: 0; }
  .compact .c-text { min-width: 0; flex: 1; }
  .compact .badges { justify-content: flex-start; margin-top: 6px; }
  .compact .later { margin-top: 4px; font-size: 0.85em; color: var(--secondary-text-color); }
  .compact .warn.icon { margin-top: 6px; }
  .compact .c-text > p { margin: 8px 0 0; }
  @container (max-width: 260px) {
    .compact section { flex-direction: column; text-align: center; }
    .compact .badges { justify-content: center; }
  }

  .list { padding: 4px 0; }
  .l-row { display: grid; grid-template-columns: var(--cols); gap: 8px; align-items: center;
           padding: 6px 16px; min-height: 44px; }
  .l-row + .l-row { border-top: 1px solid var(--divider-color); }
  .l-temp { text-align: right; white-space: nowrap; color: var(--primary-text-color); }
  .l-icons { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
  .list .badge { width: 28px; height: 28px; }
  .list .badge img { width: 20px; height: 20px; }
`;

// Built on the HTMLElement that is current when the card registers (see register below).
const makeCard = (Base) => class LayercastCard extends Base {
  static getConfigForm() {
    return {
      schema: [
        { name: "title", selector: { text: {} } },
        {
          name: "entities",
          required: true,
          selector: { entity: { multiple: true, domain: "sensor", integration: "layercast" } },
        },
        {
          name: "layout",
          selector: {
            select: {
              mode: "dropdown",
              options: [
                { value: "auto", label: "Auto" },
                ...Object.entries(LAYOUTS).map(([value, layout]) => ({ value, label: layout.label })),
              ],
            },
          },
        },
        { name: "figure", selector: { select: { options: Object.keys(FIGURES), mode: "dropdown" } } },
        { name: "figure_url", selector: { text: {} } },
        { name: "show_weather", selector: { boolean: {} } },
        { name: "show_warnings", selector: { boolean: {} } },
      ],
      // The editor passes a localize function, not hass: take the language of the page.
      computeLabel: (schema) => (TEXT[uiLanguage().slice(0, 2)] || TEXT.en)[schema.name] ?? schema.name,
      computeHelper: (schema) =>
        schema.name === "layout" ? (TEXT[uiLanguage().slice(0, 2)] || TEXT.en).layoutHelp : undefined,
    };
  }

  static getStubConfig(hass) {
    const entities = Object.entries(hass.states)
      .filter(([id, s]) => id.startsWith("sensor.") && s.attributes.period !== undefined && Array.isArray(s.attributes.items))
      .map(([id]) => id);
    return { entities: entities.slice(0, 3), layout: "auto", figure: "neutral", show_weather: true, show_warnings: true };
  }

  setConfig(config) {
    if (!Array.isArray(config.entities) || !config.entities.length) {
      throw new Error("Select at least one Layercast period sensor (entities)");
    }
    const layout = config.layout || "auto";
    if (layout !== "auto" && !LAYOUTS[layout]) {
      throw new Error(`Unknown layout: ${layout}`);
    }
    const figure = config.figure || "neutral";
    if (!config.figure_url && !FIGURES[figure]) {
      throw new Error(`Unknown figure: ${figure}`);
    }
    this._config = { ...config, layout, figure };
    this._signature = null;

    // figure_url is the folder of an own figure; make sure it ends with a slash.
    const url = config.figure_url ? config.figure_url.replace(/\/?$/, "/") : FIGURES[figure];
    if (url !== this._figureUrl) {
      this._figureUrl = url;
      this._figure = undefined; // loading
      loadFigure(url).then((figureData) => {
        if (url !== this._figureUrl) return; // the config changed meanwhile
        this._figure = figureData;
        this._render();
      });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // Home Assistant sets hass on every state change; only redraw when ours changed.
    const signature = this._config?.entities.map((id) => hass.states[id]?.last_updated).join("|");
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  connectedCallback() {
    // The width of the card decides the view of layout "auto".
    if (typeof ResizeObserver === "undefined" || this._resizeObserver) return;
    this._resizeObserver = new ResizeObserver((entries) => this._setWidth(entries[0]?.contentRect?.width));
    this._resizeObserver.observe(this);
  }

  disconnectedCallback() {
    this._resizeObserver?.disconnect();
    this._resizeObserver = undefined;
  }

  _setWidth(width) {
    if (!(width > 0)) return; // hidden (display: none)
    const level = autoLevel(width, this._level);
    if (level === this._level) return;
    this._level = level;
    if (this._config?.layout === "auto") this._render();
  }

  /* The layout that is shown: the configured one, or for "auto" the one that fits the width. */
  _layoutName() {
    const layout = this._config?.layout;
    if (layout !== "auto") return layout;
    if (this._level === undefined && this.clientWidth > 0) this._level = autoLevel(this.clientWidth);
    return AUTO_LAYOUTS[this._level ?? AUTO_LAYOUTS.length - 1];
  }

  _now() {
    return new Date();
  }

  getCardSize() {
    const layout = LAYOUTS[this._layoutName()];
    return layout ? layout.size(this._config.entities.length) : 6;
  }

  /* Size in the sections view. "auto" must not depend on the view it picks (that depends on the
   * width, which depends on this): it is wide by default and can be resized narrower. */
  getGridOptions() {
    const layout = this._config?.layout;
    return layout && layout !== "auto" ? { ...LAYOUTS[layout].grid } : { columns: 12, min_columns: 3 };
  }

  /* A tap on a period opens its sensor: the items, the weather values, the unsupported rules. */
  _openMoreInfo(event) {
    if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
    const entityId = event.target?.closest?.("[data-entity]")?.dataset?.entity;
    if (!entityId) return;
    if (event.type === "keydown") event.preventDefault();
    this.dispatchEvent(
      new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId } }),
    );
  }

  _render() {
    if (!this._config || !this._hass) return;
    const hass = this._hass;
    const language = hass.locale?.language || "en";
    const t = TEXT[language.slice(0, 2)] || TEXT.en;
    const timeZone = hass.config?.time_zone;
    const fahrenheit = hass.config?.unit_system?.temperature === "°F";
    const inches = hass.config?.unit_system?.length === "mi";
    const now = () => this._now();
    const ymd = (date) => date.toLocaleDateString("en-CA", { timeZone });
    const num = (c) => Math.round(fahrenheit ? (c * 9) / 5 + 32 : c);
    const unit = fahrenheit ? "°F" : "°C";
    const ctx = {
      t,
      now,
      ymd,
      num,
      showWeather: this._config.show_weather !== false,
      showWarnings: this._config.show_warnings !== false,
      // undefined while loading, null if it could not be loaded (everything becomes badges)
      figure: this._figure,
      // Sensor values are always in °C; show them in the user's unit.
      temp: (c) => `${num(c)}${unit}`,
      range: (lo, hi, short = false) => {
        if (lo == null || hi == null) return "";
        if (num(lo) === num(hi)) return `${num(lo)}${unit}`;
        return short ? `${num(lo)}–${num(hi)}${unit}` : `${num(lo)}${unit} – ${num(hi)}${unit}`;
      },
      // Rain in mm; empty if there is none worth showing.
      amount: (mm) => {
        if (!(mm > 0)) return "";
        const value = inches ? mm / 25.4 : mm;
        const digits = inches ? 2 : 1;
        if (Number(value.toFixed(digits)) === 0) return "";
        return `${value.toLocaleString(language, { maximumFractionDigits: digits })} ${inches ? "in" : "mm"}`;
      },
      // A label for the day when the period is not today: "Tomorrow", then the weekday.
      time: (iso, withDay = true) => {
        const date = new Date(iso);
        const clock = date.toLocaleTimeString(language, { hour: "2-digit", minute: "2-digit", timeZone });
        if (!withDay) return clock;
        const today = ymd(now());
        const day = ymd(date);
        if (day === today) return clock;
        const [y, m, d] = today.split("-").map(Number);
        const tomorrow = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
        const label = day === tomorrow ? t.tomorrow : date.toLocaleDateString(language, { weekday: "short", timeZone });
        return `${label} ${clock}`;
      },
    };

    const periods = [];
    let errors = this._figure === null ? `<div class="error">${esc(t.figureFailed(this._figureUrl))}</div>` : "";
    for (const id of this._config.entities) {
      const entity = hass.states[id];
      if (entity) periods.push({ id, state: entity.state, attrs: { period: entity.attributes.friendly_name, ...entity.attributes } });
      else errors += `<div class="error">${esc(t.missing(id))}</div>`;
    }

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (event) => this._openMoreInfo(event));
      this.shadowRoot.addEventListener("keydown", (event) => this._openMoreInfo(event));
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card${this._config.title ? ` header="${esc(this._config.title)}"` : ""}>
        ${errors}${periods.length ? LAYOUTS[this._layoutName()].render(periods, ctx) : ""}
      </ha-card>`;
    // A badge image can be missing (custom URL): fall back to the generic icon.
    for (const img of this.shadowRoot.querySelectorAll("img[data-fallback]")) {
      img.addEventListener("error", () => { img.src = img.dataset.fallback; }, { once: true });
    }
  }
};

/* Home Assistant loads this file at the same time as its app. The app replaces the custom
 * element registry (scoped registries) and only looks in the new one. An element defined
 * before that is never found ("Custom element not found"). So wait for the app, then define. */
function register() {
  if (customElements.get("layercast-card")) return;
  customElements.define("layercast-card", makeCard(HTMLElement));
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "layercast-card",
    name: "Layercast",
    description: "A person dressed for the periods of your day",
    preview: true,
  });
}

if (customElements.get("home-assistant")) register();
else customElements.whenDefined("home-assistant").then(register);
