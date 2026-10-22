// Renders a contact sheet of the layer combinations of a figure to docs/figures.png, to check
// how garments fit each other. Same setup as render.mjs (CHROMIUM_PATH / CHROMIUM_ARGS work too).
//   node figures.mjs                        all sections of the neutral figure -> ../figures.png
//   node figures.mjs --set tops --out /tmp/tops.png --figure mycomic
//   node figures.mjs --dir ~/figures/mycomic --out /tmp/sheet.png      a figure folder from anywhere
//   node figures.mjs --set tops --scale 3 --clip 16,53,200,420     zoom into a region (x,y,w,h)
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, resolve } from "node:path";
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const { values: args } = parseArgs({
  options: {
    set: { type: "string" },
    figure: { type: "string" },
    dir: { type: "string" },
    out: { type: "string" },
    scale: { type: "string" },
    clip: { type: "string" },
  },
});
const here = fileURLToPath(new URL(".", import.meta.url));
const www = join(here, "../../custom_components/layercast/www");
const types = { ".html": "text/html", ".js": "text/javascript", ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png" };

const server = createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://localhost");
  // /figure-dir/ is the folder given with --dir: a figure that is not part of the integration.
  const file = pathname.startsWith("/layercast_static/")
    ? join(www, pathname.slice("/layercast_static".length))
    : pathname.startsWith("/figure-dir/") && args.dir
      ? join(resolve(args.dir), pathname.slice("/figure-dir".length))
      : join(here, pathname === "/" ? "figures.html" : pathname);
  try {
    res.setHeader("content-type", types[extname(file)] ?? "application/octet-stream");
    res.end(await readFile(file));
  } catch {
    res.statusCode = 404;
    res.end();
  }
});
await new Promise((resolve) => server.listen(0, resolve));

let browser;
try {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: (process.env.CHROMIUM_ARGS ?? "").split(" ").filter(Boolean),
  });
  const page = await browser.newPage({
    viewport: { width: 1712, height: 600 },
    deviceScaleFactor: Number(args.scale ?? 1),
  });
  page.on("pageerror", (e) => console.error("page error:", e.message));
  const query = new URLSearchParams({ ...(args.set && { set: args.set }), ...(args.figure && { figure: args.figure }), ...(args.dir && { dir: "1" }) });
  await page.goto(`http://localhost:${server.address().port}/?${query}`);
  await page.waitForSelector("body[data-ready=true]");
  const path = args.out ?? join(here, "../figures.png");
  if (args.clip) {
    const [x, y, width, height] = args.clip.split(",").map(Number);
    await page.screenshot({ path, clip: { x, y, width, height }, fullPage: true });
  } else {
    await page.locator("body").screenshot({ path });
  }
} finally {
  await browser?.close();
  server.close();
}
