#!/usr/bin/env node
// NF-003 OSS-Clearing gate for frontend/ — mirrors check_licenses_python.py.
// Every production dependency must carry a license from
// license_allowlist_node.txt, or be a named, justified exception in
// license_exceptions_node.json (docs/OSS-CLEARING.md documents the same
// list for humans).
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));

const allowlist = new Set(
  readFileSync(path.join(scriptDir, "license_allowlist_node.txt"), "utf-8")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
);
const exceptions = JSON.parse(
  readFileSync(path.join(scriptDir, "license_exceptions_node.json"), "utf-8")
);

const raw = execFileSync(
  "npx",
  ["--yes", "license-checker", "--production", "--json"],
  { cwd: path.join(scriptDir, "..", "frontend"), encoding: "utf-8", maxBuffer: 1024 * 1024 * 32 }
);
const packages = JSON.parse(raw);

const violations = [];
const blocked = [];
const accepted = [];

for (const [key, info] of Object.entries(packages)) {
  const name = key.replace(/@[^@]+$/, "");
  const licenseStr = Array.isArray(info.licenses) ? info.licenses.join(" OR ") : String(info.licenses);

  if (name in exceptions) {
    const entry = exceptions[name];
    (entry.blocking ? blocked : accepted).push([name, entry]);
    continue;
  }

  if (!allowlist.has(licenseStr)) {
    violations.push([key, licenseStr]);
  }
}

if (accepted.length) {
  console.log("Akzeptierte, dokumentierte Ausnahmen (siehe docs/OSS-CLEARING.md):");
  for (const [name, entry] of accepted) {
    console.log(`  - ${name}: ${entry.license}`);
  }
  console.log("");
}

let exitCode = 0;

if (blocked.length) {
  console.log("BLOCKIERENDE Lizenz-Ausnahmen (Entscheidung steht aus):");
  for (const [name, entry] of blocked) {
    console.log(`  - ${name}: ${entry.license}`);
    console.log(`    ${entry.rationale}`);
  }
  console.log("");
  exitCode = 1;
}

if (violations.length) {
  console.log("Nicht erlaubte/unbekannte Lizenzen (weder Allowlist noch Ausnahmeliste):");
  for (const [key, licenseStr] of violations) {
    console.log(`  - ${key}: ${licenseStr}`);
  }
  console.log("");
  console.log(
    "Neues Paket mit permissiver Lizenz? scripts/license_allowlist_node.txt ergaenzen. " +
      "Neues Paket mit Copyleft-Lizenz? scripts/license_exceptions_node.json + " +
      "docs/OSS-CLEARING.md ergaenzen und mit dem Auftraggeber klaeren."
  );
  exitCode = 1;
}

if (exitCode === 0) {
  console.log(`OK — ${Object.keys(packages).length} Pakete, alle Lizenzen erlaubt oder als Ausnahme akzeptiert.`);
}

process.exit(exitCode);
