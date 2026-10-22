// Renders the real card with mock data to docs/screenshot.png and docs/views/*.png.
//   npm install --no-save playwright && npx playwright install chromium && node render.mjs
// To use an installed browser instead, set CHROMIUM_PATH=/path/to/chrome and, if it needs
// them, CHROMIUM_ARGS="--no-sandbox ..." (a Nix-provided Chrome has no setuid sandbox).
import { createServer } from "node:http";
import { mkdir, readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = fileURLToPath(new URL(".", import.meta.url));
const www = join(here, "../../custom_components/layercast/www");
const types = { ".html": "text/html", ".js": "text/javascript", ".svg": "image/svg+xml" };

// Serve index.html, and the integration's www folder at the URL Home Assistant uses.
const server = createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://localhost");
  const file = pathname.startsWith("/layercast_static/")
    ? join(www, pathname.slice("/layercast_static".length))
    : join(here, pathname === "/" ? "index.html" : pathname);
  try {
    res.setHeader("content-type", types[extname(file)] ?? "application/octet-stream");
    res.end(await readFile(file));
  } catch {
    res.statusCode = 404;
    res.end();
  }
});
await new Promise((resolve) => server.listen(0, resolve));

// The README pictures: file, and the query of index.html (layout, width of the card, scenario).
const SHOTS = [
  { file: "../screenshot.png", query: { layout: "timeline", width: 900 } },
  { file: "../views/timeline-small.png", query: { layout: "timeline-small", width: 480 } },
  { file: "../views/compact.png", query: { layout: "compact", width: 420 } },
  { file: "../views/list.png", query: { layout: "list", width: 560 } },
  { file: "../views/plain.png", query: { layout: "timeline", width: 900, scenario: "plain" } },
];

let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: (process.env.CHROMIUM_ARGS ?? "").split(" ").filter(Boolean),
  });
  await mkdir(join(here, "../views"), { recursive: true });
  for (const { file, query } of SHOTS) {
    // The page has 24 px of padding around the card.
    const page = await browser.newPage({ viewport: { width: query.width + 48, height: 400 }, deviceScaleFactor: 2 });
    page.on("console", (m) => console.log("page:", m.text()));
    page.on("pageerror", (e) => console.error("page error:", e.message));
    await page.goto(`http://localhost:${server.address().port}/?${new URLSearchParams(query)}`);
    await page.waitForSelector("body[data-ready=true]");
    await page.locator("body").screenshot({ path: join(here, file) });
    await page.close();
  }
} finally {
  await browser?.close();
  server.close();
}
