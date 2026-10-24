// Tests for the card. Run with: node --test tests/card.test.mjs
// No browser needed: just enough of the DOM is faked to load the card and render it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const WWW = new URL("../custom_components/layercast/www/", import.meta.url);
const CARD = new URL("layercast-card.js", WWW);

/* A custom element registry with whenDefined, like the browser's. */
class Registry {
  elements = new Map();
  waiting = new Map();
  define(name, cls) {
    this.elements.set(name, cls);
    (this.waiting.get(name) || []).forEach((resolve) => resolve(cls));
  }
  get(name) {
    return this.elements.get(name);
  }
  whenDefined(name) {
    if (this.elements.has(name)) return Promise.resolve(this.elements.get(name));
    return new Promise((resolve) => this.waiting.set(name, [...(this.waiting.get(name) || []), resolve]));
  }
}

// Run a fresh copy of the card file, as the browser does when it loads it. (Not import():
// Node would run the .js file as CommonJS and cache it.)
const source = readFileSync(CARD, "utf8");
async function loadCard() {
  globalThis.window = globalThis;
  globalThis.HTMLElement = class {
    events = [];
    attachShadow() {
      const handlers = {};
      this.shadowRoot = {
        innerHTML: "",
        querySelectorAll: () => [],
        addEventListener: (type, handler) => (handlers[type] = handler),
        dispatch: (event) => handlers[event.type](event),
      };
      return this.shadowRoot;
    }
    dispatchEvent(event) {
      this.events.push(event);
    }
  };
  globalThis.customCards = undefined;
  new Function(source)();
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("the card ends up in the registry Home Assistant installs after it", async () => {
  // The card file loads first and finds the browser's own registry...
  const original = new Registry();
  globalThis.customElements = original;
  await loadCard();
  assert.equal(original.get("layercast-card"), undefined, "must not register before the app is up");

  // ...then the app swaps in its scoped registry and defines <home-assistant> in it. Like the
  // real polyfill, that also defines a stand-in in the native registry.
  const scoped = new Registry();
  globalThis.customElements = scoped;
  scoped.define("home-assistant", class {});
  original.define("home-assistant", class {});
  await tick();

  assert.ok(scoped.get("layercast-card"), "the card must be in the registry that is current");
  assert.equal(globalThis.customCards.filter((c) => c.type === "layercast-card").length, 1);
});

test("the card registers at once when the app is already running", async () => {
  const registry = new Registry();
  registry.define("home-assistant", class {});
  globalThis.customElements = registry;
  await loadCard();
  assert.ok(registry.get("layercast-card"));
});

// --- rendering -------------------------------------------------------------------------

// Everything happens on 2026-10-22, in UTC. It is 12:30, so the "Day" period is running.
const NOW = new Date("2026-10-22T12:30:00Z");
const at = (hour, day = 22) => new Date(Date.UTC(2026, 9, day, hour)).toISOString();

const Jacket = { name: "Jacket", image: "jacket" };
const Sunscreen = { name: "Sunscreen", image: "sunscreen" };
const Umbrella = { name: "Umbrella", image: "umbrella" };
const RainJacket = { name: "Rain jacket", image: "rain_jacket" };
const Boots = { name: "Boots", image: "boots" };

const EVERYTHING = { temp_min: 5, temp_max: 9, feels_min: 2, feels_max: 7, rain_probability_max: 40, uv_max: 5 };

/* A period sensor, as the integration produces it. */
const period = (name, from, to, items, { values = EVERYTHING, day = 22, ...extra } = {}) => ({
  state: items.map((i) => i.name).join(", ") || "-",
  last_updated: name,
  attributes: {
    friendly_name: name,
    period: name,
    start: at(from, day),
    end: at(to, day),
    hours: to - from,
    items,
    unsupported: [],
    values,
    ...extra,
  },
});

const DEFAULT_STATES = () => ({
  "sensor.a": period("Morning", 7, 11, [Jacket, Sunscreen], { unsupported: ["Sunscreen"] }),
});

/* Three periods of one day with different items. */
const DAY_STATES = (day = 22) => ({
  "sensor.morning": period("Morning", 7, 11, [Jacket], { day }),
  "sensor.day": period("Day", 11, 17, [Jacket, Sunscreen], { day }),
  "sensor.evening": period("Evening", 17, 22, [Jacket, Umbrella, RainJacket], { day }),
});

async function mount(config, states = DEFAULT_STATES(), { now = NOW, language = "en", unit_system } = {}) {
  const registry = new Registry();
  registry.define("home-assistant", class {});
  globalThis.customElements = registry;
  globalThis.fetch = async (url) => ({
    ok: true,
    json: async () => JSON.parse(readFileSync(new URL(url.replace("/layercast_static/", ""), WWW), "utf8")),
  });
  await loadCard();
  const card = new (registry.get("layercast-card"))();
  card._now = () => now;
  card.setConfig({ entities: Object.keys(states), ...config });
  card.hass = {
    states,
    locale: { language },
    config: { time_zone: "UTC", unit_system: unit_system ?? { temperature: "°C", length: "km" } },
  };
  await tick();
  return card;
}

const html = (card) => card.shadowRoot.innerHTML.replace(/<style>[\s\S]*<\/style>/, "").replace(/\s+/g, " ");
const render = async (...args) => html(await mount(...args));

test("weather values are shown by default", async () => {
  const out = await render({});
  assert.match(out, /5°C – 9°C/);
  assert.match(out, /feels 2–7°C/);
  assert.match(out, /40%/);
  assert.match(out, /UV 5/);
});

test("show_weather: false hides only the weather values", async () => {
  const out = await render({ show_weather: false });
  assert.doesNotMatch(out, /5°C/);
  assert.doesNotMatch(out, /feels/);
  assert.doesNotMatch(out, /40%/);
  assert.doesNotMatch(out, /UV 5/);
  assert.match(out, /Morning/); // name
  assert.match(out, /–/); // time range
  assert.match(out, /neutral\/jacket\.svg/); // figure
  assert.match(out, /data-name="Sunscreen"/); // badge
  assert.match(out, /class="warn"/); // unsupported warning
});

test("items without a layer become badges, the others are drawn", async () => {
  const out = await render({});
  assert.match(out, /neutral\/jacket\.svg" alt="" style="z-index:40"/);
  assert.match(out, /data-name="Sunscreen"[^>]*> <img src="\/layercast_static\/icons\/sunscreen\.svg"/);
});

test("the card host has its own stacking context", async () => {
  // Without it the z-index of figure layers and badge tooltips would be compared in the root
  // context and would end up above the Home Assistant app bar (z-index 4).
  const card = await mount({}, DAY_STATES());
  assert.match(card.shadowRoot.innerHTML, /:host \{[^}]*isolation: isolate/);
});

// --- the rows of the timeline: the figures must start at the same height --------------------

const rowsAboveFigure = (out) =>
  out
    .split("<section ")
    .slice(1)
    .map((column) => [...column.matchAll(/<(?:div|h3) class="((?:row|body)[^"]*)"/g)].map((m) => m[1]));

const NO_FORECAST = {
  state: "unknown",
  last_updated: "c",
  attributes: { friendly_name: "Evening", period: "Evening", start: at(17), end: at(22), hours: 0, items: [], unsupported: [], values: {} },
};

test("every column has the same rows, whatever it has to show", async () => {
  const states = {
    // feels-like equals the temperature, no rain or UV values
    "sensor.a": period("Morning", 7, 11, [Jacket], { values: { temp_min: 5, temp_max: 5, feels_min: 5, feels_max: 5 } }),
    "sensor.b": period("Day", 11, 17, [Jacket]), // everything
    "sensor.c": NO_FORECAST,
  };
  const withWeather = rowsAboveFigure(await render({ layout: "timeline" }, states));
  assert.equal(withWeather.length, 3);
  assert.deepEqual(withWeather[1], withWeather[0]);
  assert.deepEqual(withWeather[2], withWeather[0]);
  assert.equal(withWeather[0].length, 5); // name, time, temperature, detail line, body
  assert.equal(withWeather[0].at(-1), "body");

  const without = rowsAboveFigure(await render({ layout: "timeline", show_weather: false }, states));
  assert.deepEqual(without[0], without[2]);
  assert.equal(without[0].length, 3); // name, time, body
});

test("a row that no column has anything for is not drawn", async () => {
  const bare = { temp_min: 5, temp_max: 9, feels_min: 5, feels_max: 9 }; // nothing for the detail line
  const states = {
    "sensor.a": period("Morning", 7, 11, [Jacket], { values: bare }),
    "sensor.b": period("Day", 11, 17, [Jacket], { values: bare }),
  };
  const rows = rowsAboveFigure(await render({ layout: "timeline" }, states));
  assert.equal(rows[0].length, 4); // name, time, temperature, body: no detail line at all
  assert.ok(!rows[0].some((r) => r.includes("detail")));

  const none = rowsAboveFigure(await render({ layout: "timeline" }, { "sensor.c": NO_FORECAST }));
  assert.equal(none[0].length, 3); // not even a temperature row
});

// --- the detail line ----------------------------------------------------------------------

const detailOf = async (values, options) => {
  const out = await render({ layout: "timeline" }, { "sensor.a": period("Day", 11, 17, [Jacket], { values }) }, options);
  return out.match(/class="row muted detail" title="([^"]*)"/)?.[1];
};

test("the detail line joins feels-like, rain and UV, and leaves out what is missing", async () => {
  assert.equal(await detailOf(EVERYTHING), "feels 2–7°C · 40% · UV 5");
  assert.equal(await detailOf({ ...EVERYTHING, uv_max: 0 }), "feels 2–7°C · 40%");
  assert.equal(await detailOf({ ...EVERYTHING, feels_min: 5, feels_max: 9, uv_max: 0 }), "40%");
  assert.equal(await detailOf({ temp_min: 5, temp_max: 9, uv_max: 3 }), "UV 3");
  assert.equal(await detailOf({ temp_min: 5, temp_max: 9 }), undefined);
});

test("without a rain probability the rain amount is shown instead", async () => {
  const dry = { temp_min: 5, temp_max: 9, feels_min: 5, feels_max: 9 };
  assert.equal(await detailOf({ ...dry, rain_sum: 1.24 }), "1.2 mm");
  assert.equal(await detailOf({ ...dry, rain_sum: 1.24, uv_max: 2 }), "1.2 mm · UV 2");
  assert.equal(await detailOf({ ...dry, rain_sum: 0 }), undefined);
  assert.equal(await detailOf({ ...dry, rain_sum: 0.04 }), undefined); // would round to 0.0 mm
  assert.equal(await detailOf({ ...dry, rain_sum: 1.24, rain_probability_max: 30 }), "30%"); // probability wins
  const imperial = { temperature: "°C", length: "mi" };
  assert.equal(await detailOf({ ...dry, rain_sum: 25.4 }, { unit_system: imperial }), "1 in");
});

test("temperatures follow the unit system", async () => {
  const out = await render({ layout: "timeline" }, DEFAULT_STATES(), { unit_system: { temperature: "°F" } });
  assert.match(out, /41°F – 48°F/);
  assert.match(out, /feels 36–45°F/);
});

// --- warnings ---------------------------------------------------------------------------------

test("a warning names the rules and can be hidden with show_warnings", async () => {
  const shown = await render({ layout: "timeline" });
  assert.match(shown, /class="warn" title="[^"]*Sunscreen"/);
  assert.match(shown, /1 rule\(s\) cannot be evaluated/);

  const hidden = await render({ layout: "timeline", show_warnings: false });
  assert.doesNotMatch(hidden, /class="warn/);
  assert.match(hidden, /5°C – 9°C/); // everything else stays
});

test("the small views only show a warning icon", async () => {
  for (const layout of ["timeline-small", "compact", "list"]) {
    const out = await render({ layout });
    assert.match(out, /class="warn icon" title="[^"]*Sunscreen"/, layout);
    assert.doesNotMatch(out, /cannot be evaluated/, layout);
  }
});

// --- days -------------------------------------------------------------------------------------

test("a period that is not today says so", async () => {
  const states = { "sensor.a": period("Morning", 7, 11, [Jacket], { day: 23 }), "sensor.b": period("Later", 7, 11, [Jacket], { day: 25 }) };
  const out = await render({ layout: "timeline" }, states);
  assert.match(out, /Tomorrow 07:00/);
  assert.match(out, /Sun 07:00/); // 2026-10-25
  assert.match(await render({ layout: "timeline" }, states, { language: "de" }), /morgen 07:00/);
  assert.doesNotMatch(await render({ layout: "timeline" }), /Tomorrow|Sun 07/); // today: no label
});

// --- compact: the period that is running now ----------------------------------------------

const pickedPeriod = async (states, now) => {
  const out = await render({ layout: "compact" }, states, { now });
  assert.equal((out.match(/<h3/g) || []).length, 1); // one period only
  return out.match(/<h3 class="row name">([^<]*)</)[1];
};

test("compact shows the running period, or else the next one", async () => {
  const states = DAY_STATES();
  assert.equal(await pickedPeriod(states, new Date("2026-10-22T12:30:00Z")), "Day");
  assert.equal(await pickedPeriod(states, new Date("2026-10-22T07:00:00Z")), "Morning"); // starts now
  assert.equal(await pickedPeriod(states, new Date("2026-10-22T11:00:00Z")), "Day"); // morning ended
  assert.equal(await pickedPeriod(states, new Date("2026-10-22T05:00:00Z")), "Morning"); // next to start
  assert.equal(await pickedPeriod(states, new Date("2026-10-22T11:30:00Z")), "Day");
  // between periods: the next one
  const gap = { "sensor.a": period("Morning", 7, 9, [Jacket]), "sensor.b": period("Evening", 17, 22, [Jacket]) };
  assert.equal(await pickedPeriod(gap, new Date("2026-10-22T12:00:00Z")), "Evening");
});

test("at night compact shows tomorrow's first period, and says so", async () => {
  // The sensors have rolled over: all periods are tomorrow's.
  const states = DAY_STATES(23);
  const out = await render({ layout: "compact" }, states, { now: new Date("2026-10-22T23:00:00Z") });
  assert.match(out, /<h3 class="row name">Morning</);
  assert.match(out, /Tomorrow 07:00/);
});

test("if periods overlap, compact shows the one that started last", async () => {
  const states = { "sensor.a": period("All day", 6, 22, [Jacket]), "sensor.b": period("Lunch", 12, 14, [Jacket]) };
  assert.equal(await pickedPeriod(states, NOW), "Lunch");
});

const laterOf = async (states, now) => (await render({ layout: "compact" }, states, { now })).match(/class="later" title="([^"]*)">([^<]*)</);

test("compact lists what only later periods of the day need", async () => {
  const states = DAY_STATES();
  // Day (jacket, sunscreen): the evening adds the umbrella and the rain jacket.
  let later = await laterOf(states, NOW);
  assert.equal(later[1], "Umbrella, Rain jacket");
  assert.equal(later[2], "Later: + Umbrella, Rain jacket");
  // Morning (jacket): sunscreen from the day, then the evening items, each once.
  later = await laterOf(states, new Date("2026-10-22T08:00:00Z"));
  assert.equal(later[1], "Sunscreen, Umbrella, Rain jacket");
  // Evening: nothing is left of the day.
  assert.equal(await laterOf(states, new Date("2026-10-22T18:00:00Z")), null);
});

test("compact does not list periods of another day or without a forecast", async () => {
  const states = {
    "sensor.a": period("Day", 11, 17, [Jacket]),
    "sensor.b": period("Tomorrow", 7, 11, [Umbrella], { day: 23 }),
    "sensor.c": NO_FORECAST,
  };
  assert.equal(await laterOf(states, NOW), null);
});

test("compact shortens a long list of later items", async () => {
  const many = [Umbrella, RainJacket, Boots, Sunscreen, { name: "Gloves", image: "gloves" }];
  const states = { "sensor.a": period("Day", 11, 17, [Jacket]), "sensor.b": period("Evening", 17, 22, [Jacket, ...many]) };
  const later = await laterOf(states, NOW);
  assert.equal(later[2], "Later: + Umbrella, Rain jacket, Boots, …");
  assert.equal(later[1], "Umbrella, Rain jacket, Boots, Sunscreen, Gloves"); // all of them on hover
});

test("compact shows the figure, the weather and the badges of that period", async () => {
  const out = await render({ layout: "compact" }, DAY_STATES());
  assert.match(out, /class="compact"/);
  assert.match(out, /neutral\/jacket\.svg/);
  assert.match(out, /data-name="Sunscreen"/);
  assert.match(out, /5°C – 9°C/);
  assert.doesNotMatch(await render({ layout: "compact", show_weather: false }, DAY_STATES()), /5°C/);
  assert.match(await render({ layout: "compact" }, { "sensor.c": NO_FORECAST }), /No forecast for this period yet/);
});

// --- list -------------------------------------------------------------------------------------

test("list has a line per period with the item icons, and no figure", async () => {
  const out = await render({ layout: "list" }, DAY_STATES());
  assert.equal((out.match(/class="l-row"/g) || []).length, 3);
  assert.ok(out.indexOf(">Morning<") < out.indexOf(">Day<") && out.indexOf(">Day<") < out.indexOf(">Evening<"));
  assert.doesNotMatch(out, /class="figure"/);
  assert.match(out, /icons\/umbrella\.svg/);
  assert.match(out, /data-name="Rain jacket"/);
  assert.equal((out.match(/class="l-temp"/g) || []).length, 3);
  assert.match(out, /class="l-temp">5–9°C</); // the short form: the line is narrow
  assert.doesNotMatch(await render({ layout: "list", show_weather: false }, DAY_STATES()), /l-temp/);
  assert.match(await render({ layout: "list" }, { "sensor.c": NO_FORECAST }), /No forecast for this period yet/);
});

test("the small timeline has name and temperature, and the badges", async () => {
  const out = await render({ layout: "timeline-small" }, DAY_STATES());
  assert.match(out, /class="timeline small"/);
  assert.match(out, /neutral\/jacket\.svg/);
  assert.match(out, /class="row temp">5–9°C</); // the short form: the columns are narrow
  assert.doesNotMatch(out, /class="row muted time"|class="row muted detail"/);
  assert.match(out, /title="Day 11:00/); // the time is still there, on hover
  assert.doesNotMatch(await render({ layout: "timeline-small", show_weather: false }, DAY_STATES()), /5°C/);
});

// --- auto ---------------------------------------------------------------------------------------

const viewOf = (card) => (html(card).match(/class="(compact|timeline small|timeline|list)"/) || [])[1];

test("auto picks the view by the width of the card", async () => {
  const card = await mount({}, DAY_STATES());
  assert.equal(viewOf(card), "timeline"); // width not known yet: the full view
  card._setWidth(700);
  assert.equal(viewOf(card), "timeline");
  card._setWidth(400);
  assert.equal(viewOf(card), "timeline small");
  card._setWidth(300);
  assert.equal(viewOf(card), "compact");
  card._setWidth(900);
  assert.equal(viewOf(card), "timeline");
  card._setWidth(0); // hidden: ignored
  assert.equal(viewOf(card), "timeline");
});

test("auto does not flip back and forth close to a limit", async () => {
  const card = await mount({}, DAY_STATES());
  card._setWidth(700);
  for (const [width, view] of [[530, "timeline"], [510, "timeline"], [501, "timeline"], [499, "timeline small"], [515, "timeline small"], [539, "timeline small"], [541, "timeline"]]) {
    card._setWidth(width);
    assert.equal(viewOf(card), view, `${width}px`);
  }
  card._setWidth(250);
  for (const [width, view] of [[310, "compact"], [339, "compact"], [341, "timeline small"], [325, "timeline small"], [301, "timeline small"], [299, "compact"]]) {
    card._setWidth(width);
    assert.equal(viewOf(card), view, `${width}px`);
  }
});

test("a configured layout ignores the width", async () => {
  const card = await mount({ layout: "list" }, DAY_STATES());
  card._setWidth(250);
  assert.equal(viewOf(card), "list");
  card._setWidth(900);
  assert.equal(viewOf(card), "list");
});

// --- sizes ----------------------------------------------------------------------------------------

test("every view reports its size", async () => {
  const sizes = {};
  for (const layout of ["timeline", "timeline-small", "compact", "list", "auto"]) {
    const card = await mount({ layout }, DAY_STATES());
    sizes[layout] = [card.getGridOptions(), card.getCardSize()];
  }
  assert.deepEqual(sizes.timeline[0], { columns: 12, min_columns: 6 });
  assert.deepEqual(sizes["timeline-small"][0], { columns: 12, min_columns: 3 });
  assert.deepEqual(sizes.compact[0], { columns: 6, min_columns: 3 });
  assert.deepEqual(sizes.list[0], { columns: 6, min_columns: 3 });
  assert.equal(sizes.list[1], 4); // 3 periods + 1
  assert.ok(sizes.timeline[1] > sizes["timeline-small"][1] && sizes["timeline-small"][1] > sizes.compact[1]);
  // auto must not depend on the view it picks, or resizing would change the size by itself
  assert.deepEqual(sizes.auto[0], { columns: 12, min_columns: 3 });
  const auto = await mount({}, DAY_STATES());
  auto._setWidth(300);
  assert.deepEqual(auto.getGridOptions(), { columns: 12, min_columns: 3 });
  assert.equal(auto.getCardSize(), sizes.compact[1]); // masonry height follows the view
});

// --- tap, editor, config ------------------------------------------------------------------------

test("a tap on a period opens its sensor", async () => {
  const card = await mount({ layout: "timeline" }, DAY_STATES());
  const section = (entity) => ({ closest: () => ({ dataset: { entity } }) });
  card.shadowRoot.dispatch({ type: "click", target: section("sensor.day") });
  assert.equal(card.events.length, 1);
  const [event] = card.events;
  assert.equal(event.type, "hass-more-info");
  assert.deepEqual(event.detail, { entityId: "sensor.day" });
  assert.ok(event.bubbles && event.composed);

  card.shadowRoot.dispatch({ type: "keydown", key: "Enter", target: section("sensor.evening"), preventDefault() {} });
  assert.equal(card.events.length, 2);
  card.shadowRoot.dispatch({ type: "keydown", key: "a", target: section("sensor.evening"), preventDefault() {} });
  card.shadowRoot.dispatch({ type: "click", target: { closest: () => null } }); // not on a period
  assert.equal(card.events.length, 2);
  for (const layout of ["compact", "list", "timeline-small"]) {
    assert.match(await render({ layout }, DAY_STATES()), /data-entity="sensor\.\w+" tabindex="0" role="button" aria-label="[^"]+"/, layout);
  }
});

test("the editor offers every view, and explains auto", async () => {
  const registry = new Registry();
  registry.define("home-assistant", class {});
  globalThis.customElements = registry;
  await loadCard();
  const Card = registry.get("layercast-card");
  const form = Card.getConfigForm();
  const layout = form.schema.find((field) => field.name === "layout");
  assert.deepEqual(
    layout.selector.select.options.map((o) => o.value),
    ["auto", "timeline", "timeline-small", "compact", "list"],
  );
  assert.ok(layout.selector.select.options.every((o) => o.label));
  assert.deepEqual(form.schema.map((f) => f.name).slice(-2), ["show_weather", "show_warnings"]);
  assert.match(form.computeHelper({ name: "layout" }), /Auto picks the view/);
  assert.equal(form.computeHelper({ name: "title" }), undefined);
  assert.equal(form.computeLabel({ name: "show_warnings" }), "Show warnings about rules that cannot be evaluated");
  assert.equal(Card.getStubConfig({ states: {} }).layout, "auto");
});

test("the layout is checked", async () => {
  const card = await mount({}, DAY_STATES());
  assert.throws(() => card.setConfig({ entities: ["sensor.day"], layout: "carousel" }), /Unknown layout/);
  assert.doesNotThrow(() => card.setConfig({ entities: ["sensor.day"], layout: "auto" }));
  assert.doesNotThrow(() => card.setConfig({ entities: ["sensor.day"] })); // auto is the default
});
