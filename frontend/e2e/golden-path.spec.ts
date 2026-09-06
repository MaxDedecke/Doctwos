/**
 * O-062: erster End-to-End-Test für den eigentlichen Kernworkflow. Bisher gab
 * es nur `login.spec.ts` und `accessibility.spec.ts` -- kein einziger Test lief
 * durch alle Schichten (Parser, Backend, Frontend) in einem Durchgang.
 *
 * Der Ablauf hier ist der versprochene goldene Pfad:
 *   COBOL-Quelle anbinden → Parser findet die Objekte → im Browser danach
 *   suchen → Treffer anklicken → Code-Ansicht öffnet die richtige Datei an der
 *   richtigen Zeile.
 *
 * Der Test braucht den laufenden Compose-Stack, weil genau dessen Zusammenspiel
 * geprüft wird: die Wissensquelle ist ein bares Git-Repository, das der Test
 * selbst unter `repos/` anlegt -- dasselbe Verzeichnis ist in `backend-api` und
 * `parser-worker` als `/repos` eingehängt (siehe docker-compose.yml), deshalb
 * genügt eine `file:///repos/...`-URL und es wird kein Netzzugang gebraucht.
 * Fehlt das Verzeichnis (Lauf gegen eine entfernte Instanz), überspringt sich
 * der Test mit einer sprechenden Begründung, statt dauerhaft rot zu stehen --
 * dieselbe Regel wie beim `requires_ollama`-Marker der Parser-Tests.
 *
 * Die Chat-Frage aus der Aufgabenbeschreibung steht im zweiten Test: sie braucht
 * ein nutzbares LLM, das eine reine Selfhosting-Installation nicht zwingend hat
 * (dieses Deployment hat Ollama bewusst deaktiviert). Er überspringt sich in dem
 * Fall mit dem Fehlertext des Servers als Begründung.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API_URL = process.env.E2E_API_URL || "http://82.165.216.180:8000";
const USERNAME = process.env.E2E_USERNAME || "testuser";
const PASSWORD = process.env.E2E_PASSWORD || "";

// Muss aus Sicht der Container `/repos` sein -- Standard ist das Bind-Mount
// `./repos` des Compose-Stacks, eine Ebene über `frontend/`.
const REPOS_DIR = process.env.E2E_REPOS_DIR || path.resolve(__dirname, "..", "..", "repos");

const RUN_ID = `${Date.now()}`;
const FIXTURE_REPO_NAME = `e2e-golden-${RUN_ID}.git`;
const FIXTURE_REPO_URL = `file:///repos/${FIXTURE_REPO_NAME}`;

/**
 * Ein winziges, aber vollständiges COBOL-Programm. Wichtig sind die Zeilen-
 * nummern: `BETRAG-PRUEFEN` beginnt in Zeile 13 -- genau darauf zielt die
 * Schlussprüfung ab, damit "öffnet an der richtigen Zeile" auch wirklich die
 * richtige Zeile meint und nicht bloß "irgendwo in der Datei".
 */
const FIXTURE_PROGRAM = [
  "       IDENTIFICATION DIVISION.",
  "       PROGRAM-ID. ZAHLUNG.",
  "       DATA DIVISION.",
  "       WORKING-STORAGE SECTION.",
  "       01  WS-BETRAG            PIC 9(7)V99.",
  "       01  WS-STATUS            PIC X(1).",
  "       PROCEDURE DIVISION.",
  "       ZAHLUNG-START.",
  "           MOVE 0 TO WS-BETRAG.",
  "           PERFORM BETRAG-PRUEFEN.",
  "           CALL 'BUCHUNG'.",
  "           STOP RUN.",
  "       BETRAG-PRUEFEN.",
  "           IF WS-BETRAG > 1000000",
  "               MOVE 'F' TO WS-STATUS",
  "           ELSE",
  "               MOVE 'O' TO WS-STATUS",
  "           END-IF.",
  "",
].join("\n");

const FIXTURE_ENTITY = "BETRAG-PRUEFEN";
const FIXTURE_FILE = "src/ZAHLUNG.CBL";
const FIXTURE_LINE = 13;

const barePath = path.join(REPOS_DIR, FIXTURE_REPO_NAME);
let workTree = "";
let createdSourceId: number | null = null;
let createdProjectId: number | null = null;

function git(cwd: string, ...args: string[]): void {
  execFileSync("git", args, { cwd, stdio: "pipe" });
}

test.beforeAll(() => {
  if (!fs.existsSync(REPOS_DIR)) {
    // Kein Grund zur Panik, nur kein lokaler Stack: der Test kann seine
    // Fixture-Quelle dann nicht dort ablegen, wo die Container sie sehen.
    return;
  }
  execFileSync("git", ["init", "--bare", "--initial-branch=main", barePath], { stdio: "pipe" });

  workTree = fs.mkdtempSync(path.join(os.tmpdir(), "doctus-e2e-"));
  git(workTree, "init", "--initial-branch=main");
  git(workTree, "config", "user.email", "e2e@doctus.local");
  git(workTree, "config", "user.name", "Doctus E2E");
  fs.mkdirSync(path.join(workTree, "src"), { recursive: true });
  fs.writeFileSync(path.join(workTree, FIXTURE_FILE), FIXTURE_PROGRAM);
  git(workTree, "add", "-A");
  git(workTree, "commit", "-m", "E2E-Golden-Path-Fixture");
  git(workTree, "push", barePath, "main");
});

test.afterAll(async ({ playwright }) => {
  // Aufräumen über eine eigene, frisch angemeldete API-Sitzung: die Seite aus
  // dem Test ist zu diesem Zeitpunkt schon geschlossen.
  if (createdSourceId !== null || createdProjectId !== null) {
    const api = await playwright.request.newContext();
    try {
      await api.post(`${API_URL}/auth/login`, { data: { username: USERNAME, password: PASSWORD } });
      if (createdSourceId !== null) await api.delete(`${API_URL}/knowledge-sources/${createdSourceId}`);
      if (createdProjectId !== null) await api.delete(`${API_URL}/projects/${createdProjectId}`);
    } finally {
      await api.dispose();
    }
  }
  fs.rmSync(barePath, { recursive: true, force: true });
  if (workTree) fs.rmSync(workTree, { recursive: true, force: true });
});

async function login(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator("#username")).toBeVisible();
  await page.locator("#username").fill(USERNAME);
  await page.locator("#password").fill(PASSWORD);
  await page.getByRole("button", { name: /Anmelden|Sign in/ }).click();
  await expect(page.locator("#project-selector")).toBeVisible({ timeout: 15_000 });
}

/** Legt Projekt + Git-Wissensquelle an und wartet, bis der Parser durch ist. */
async function ingestFixtureSource(request: APIRequestContext): Promise<number> {
  const projectResp = await request.post(`${API_URL}/projects`, { data: { name: `e2e-golden-${RUN_ID}` } });
  expect(projectResp.ok(), await projectResp.text()).toBeTruthy();
  const project = await projectResp.json();
  createdProjectId = project.id;

  const sourceResp = await request.post(`${API_URL}/knowledge-sources/git`, {
    data: { name: `E2E COBOL ${RUN_ID}`, url: FIXTURE_REPO_URL, branch: "main", project_id: project.id },
  });
  expect(sourceResp.ok(), await sourceResp.text()).toBeTruthy();
  const source = await sourceResp.json();
  createdSourceId = source.id;

  // Der Sync läuft asynchron im parser-worker -- hier wird auf den Endzustand
  // gewartet, nicht auf eine feste Zeit.
  let last: any = null;
  await expect
    .poll(
      async () => {
        const listResp = await request.get(`${API_URL}/knowledge-sources?project_id=${project.id}`);
        const sources = await listResp.json();
        last = sources.find((s: any) => s.id === source.id);
        return last?.sync_status;
      },
      { timeout: 180_000, intervals: [2_000], message: "Git-Sync des Fixture-Repos wurde nicht fertig" }
    )
    .toBe("completed");

  expect(last?.last_error, `Sync meldete einen Fehler: ${last?.last_error}`).toBeFalsy();
  expect(last?.parsed_files, "Der Parser hat keine Datei verarbeitet").toBeGreaterThan(0);

  return project.id;
}

test("goldener Pfad: COBOL-Quelle anbinden, parsen, suchen und an der richtigen Zeile öffnen", async ({ page }) => {
  test.skip(!fs.existsSync(REPOS_DIR), `Kein Compose-Bind-Mount unter ${REPOS_DIR} -- der Test braucht den lokal laufenden Stack.`);
  // Klonen, Parsen und Indizieren dauern deutlich länger als eine UI-Interaktion.
  test.setTimeout(300_000);

  await login(page);

  const projectId = await ingestFixtureSource(page.request);

  // Der Parser muss die Objekte auch wirklich persistiert haben -- die Suche
  // ist der erste Punkt, an dem Backend und Datenbank das gemeinsam bezeugen.
  let hit: any = null;
  await expect
    .poll(
      async () => {
        const resp = await page.request.get(
          `${API_URL}/search?q=${encodeURIComponent(FIXTURE_ENTITY)}&project_id=${projectId}&limit=5`
        );
        const body = await resp.json();
        hit = (body.results || []).find((r: any) => r.node_label === FIXTURE_ENTITY && r.node_type === "entity");
        return Boolean(hit);
      },
      { timeout: 120_000, intervals: [2_000], message: "Der Parser hat das COBOL-Objekt nicht indiziert" }
    )
    .toBe(true);

  expect(hit.node_meta.file_path).toBe(FIXTURE_FILE);
  expect(hit.node_meta.start_line).toBe(FIXTURE_LINE);

  // Ab hier nur noch Oberfläche: Projekt wählen, suchen, Treffer anklicken,
  // Code-Ansicht prüfen.
  await page.reload();
  await selectProject(page, `e2e-golden-${RUN_ID}`);

  await expect(page.locator("#global-search-input")).toBeVisible({ timeout: 15_000 });
  await page.locator("#global-search-input").fill(FIXTURE_ENTITY);

  const result = page.locator(`#global-search-result-entity-${hit.node_id}`);
  await expect(result).toBeVisible({ timeout: 15_000 });
  await result.click();

  await expectCodeViewAt(page, "ZAHLUNG.CBL", FIXTURE_LINE);
});

test("goldener Pfad: Chat-Antwort verweist auf die Quelle und öffnet sie an der richtigen Zeile", async ({ page }) => {
  test.skip(!fs.existsSync(REPOS_DIR), `Kein Compose-Bind-Mount unter ${REPOS_DIR} -- der Test braucht den lokal laufenden Stack.`);
  test.setTimeout(300_000);

  await login(page);

  const projectId = createdProjectId ?? (await ingestFixtureSource(page.request));
  await page.reload();
  await selectProject(page, `e2e-golden-${RUN_ID}`);

  // Vorprüfung über die API: hat diese Installation überhaupt ein nutzbares
  // LLM? Eine Selfhosting-Installation ohne Cloud-Profil und mit deaktiviertem
  // Ollama kann diesen Schritt nicht gehen -- dann wird übersprungen statt rot.
  const probe = await page.request.post(`${API_URL}/chat`, {
    data: { message: "Ping", project_id: projectId },
    timeout: 120_000,
  });
  const probeBody = await probe.text();
  const llmError = /"type":\s*"error"/.test(probeBody) ? probeBody.slice(0, 400) : null;
  test.skip(Boolean(llmError), `Diese Installation hat kein nutzbares LLM: ${llmError}`);

  await page.locator("#chat-textarea").fill(`In welcher Datei und Zeile steht ${FIXTURE_ENTITY}?`);
  await page.locator("#send-chat-message-btn").click();

  const sourceLink = page.locator("#chat-source-link-0");
  await expect(sourceLink, "Die Antwort nennt keine Quelle").toBeVisible({ timeout: 180_000 });

  const label = (await sourceLink.textContent()) || "";
  const referencedLine = Number(/L(\d+)/.exec(label)?.[1]);
  expect(Number.isFinite(referencedLine)).toBeTruthy();

  await sourceLink.click();
  await expectCodeViewAt(page, label.replace(/L\d+.*$/, "").trim(), referencedLine);
});

/**
 * Der Header-Suchschlitz und der Chat arbeiten im Kontext des ausgewählten
 * Projekts -- ohne diesen Schritt sucht die Oberfläche im Allgemein-Kontext und
 * findet die projektgebundene Entity nicht (der API-Aufruf oben dagegen schon,
 * er bekommt die project_id direkt mit).
 */
async function selectProject(page: Page, name: string): Promise<void> {
  const selector = page.locator("#project-selector");
  await expect(selector).toBeVisible({ timeout: 15_000 });
  await selector.click();
  await page.getByRole("option", { name, exact: false }).click();
  await expect(selector).toContainText(name, { timeout: 15_000 });
}

/**
 * Prüft, dass die Code-Ansicht die erwartete Datei zeigt und der Cursor in der
 * erwarteten Zeile steht. Monaco markiert die aktuelle Zeile im Zeilenlineal
 * mit `.active-line-number` -- das ist die verlässlichste im DOM sichtbare
 * Spur dafür, dass `revealLineInCenter`/`setPosition` tatsächlich gelaufen sind.
 */
async function expectCodeViewAt(page: Page, fileName: string, line: number): Promise<void> {
  await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(fileName, { exact: false }).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".monaco-editor .active-line-number").first()).toHaveText(String(line), { timeout: 30_000 });
}
