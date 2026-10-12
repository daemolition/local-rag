// Entfernt ausschliesslich die von Vite erzeugten Dateien direkt unter
// app/static/, damit ein Rebuild sauber ist. app/static/fonts/ (manuell
// gepflegte Assets) wird NIE angefasst.
import { existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const staticDir = resolve(here, "../../app/static");

const generated = [
  "index.html",
  "assets",
  "favicon.svg",
  "pcm-worklet-processor.js",
  "dist",
];

for (const name of generated) {
  const target = resolve(staticDir, name);
  if (existsSync(target)) rmSync(target, { recursive: true, force: true });
}

console.log(`Cleaned generated files in ${staticDir}`);
