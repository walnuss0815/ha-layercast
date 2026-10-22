// Renders the brand images of the integration (icon.png, logo.png and @2x variants).
// Same setup as render.mjs (CHROMIUM_PATH / CHROMIUM_ARGS work the same way).
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const out = join(fileURLToPath(new URL(".", import.meta.url)), "../../custom_components/layercast/brand");

const icon = `<svg id="icon" width="256" height="256" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#4fc3f7"/><stop offset="1" stop-color="#0277bd"/>
  </linearGradient></defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <circle cx="51" cy="14" r="7" fill="#ffee58"/>
  <g transform="translate(9 5) scale(.28)" stroke-linejoin="round" stroke-width="5">
    <rect x="72" y="60" width="16" height="30" fill="#f3c9a8"/>
    <ellipse cx="80" cy="40" rx="22" ry="25" fill="#f3c9a8"/>
    <path d="M57 38C55 8 105 8 103 38 98 26 90 22 80 22 70 22 62 26 57 38Z" fill="#5d4037"/>
    <path d="M58 70Q80 92 102 70L125 80 140 164 114 168 112 114V200H48V114L46 168 20 164 35 80Z" fill="#fff" stroke="#01579b"/>
    <path d="M80 88V200" fill="none" stroke="#4fc3f7" stroke-width="5"/>
    <path d="M55 34C55 6 105 6 105 34Z" fill="#ffca28" stroke="#e65100"/>
    <rect x="53" y="29" width="54" height="11" rx="5" fill="#fff3e0" stroke="#e65100"/>
  </g>
</svg>`;

const page = `<body style="margin:0;background:transparent">
  <div id="logo" style="display:inline-flex;align-items:center;gap:16px;height:128px;font:600 64px Roboto,Helvetica,Arial,sans-serif;color:#0277bd">
    <span style="display:block;width:128px;height:128px">${icon.replace('width="256" height="256"', 'width="128" height="128"')}</span>Layercast
  </div>
  <div id="big" style="width:256px;height:256px">${icon}</div>
</body>`;

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
  args: (process.env.CHROMIUM_ARGS ?? "").split(" ").filter(Boolean),
});
try {
  for (const [scale, suffix] of [[1, ""], [2, "@2x"]]) {
    const tab = await browser.newPage({ deviceScaleFactor: scale });
    await tab.setContent(page);
    await tab.locator("#logo").screenshot({ path: join(out, `logo${suffix}.png`), omitBackground: true });
    await tab.locator("#big svg").screenshot({ path: join(out, `icon${suffix}.png`), omitBackground: true });
    await tab.close();
  }
} finally {
  await browser.close();
}
