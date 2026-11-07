/** Buildprofil einer Git-Quelle als Formular (GET/PUT /knowledge-sources/{id}/build-profile).
 *
 * Das Backend speichert `{source: Fragment, paths: {Präfix: Fragment}}`; ältere Profile sind ein flaches Fragment.
 * Das Formular bearbeitet das quellweite Fragment; Abweichungen je Verzeichnis bleiben JSON, weil sie selten sind.
 * Felder, die das Formular nicht kennt (z. B. `source_columns`), bleiben beim Speichern erhalten.
 */

export type ProfileFragment = Record<string, unknown>;
export interface StoredBuildProfile { source?: ProfileFragment; paths?: Record<string, ProfileFragment> }

export interface BuildProfileView {
  source_id: number;
  build_profile: StoredBuildProfile | ProfileFragment | null;
  language_paths: Record<string, string> | null;
  note?: string;
}

export interface PreflightReport {
  source_id: number;
  files: {
    total: number;
    by_language: Record<string, Record<string, number>>;
    encodings: Record<string, number>;
  };
  parser_gaps: { pattern: string; occurrences: number; files: number; example: string }[];
  copybooks: {
    ambiguous: { name: string; references: number; example_file: string; candidates: string[] }[];
    missing: { name: string; references: number; example_file: string }[];
    duplicate_copybook_names: number;
  };
  hints: { code: string; message: string }[];
}

export const SOURCE_FORMATS = ['fixed', 'free', 'variable', 'extended'] as const;
export const LITERAL_DELIMITERS = ['both', 'apostrophe', 'quote'] as const;
export const LANGUAGE_LABELS = ['cobol', 'copybook', 'jcl', 'bms'] as const;

export interface ProfileForm {
  compiler_family: string;
  compiler_version: string;
  source_format: string; // '' = nach Inhalt erkennen
  encoding: string; // '' = UTF-8, sonst EBCDIC-Erkennung oder cp1252-Rückfall
  literal_delimiter: string;
  debug_mode: boolean;
  defines: string; // NAME=WERT je Zeile
  copy_search_order: string; // ein Verzeichnis je Zeile
  language_paths: string; // Präfix = Sprache je Zeile
  paths_json: string; // Abweichungen je Verzeichnis
}

const FORM_FIELDS = ['compiler_family', 'compiler_version', 'source_format', 'encoding', 'literal_delimiter', 'debug_mode', 'defines', 'copy_search_order'];

function split(profile: BuildProfileView['build_profile']): StoredBuildProfile {
  if (!profile) return {};
  if ('source' in profile || 'paths' in profile) return profile as StoredBuildProfile;
  return { source: profile as ProfileFragment };
}

const text = (value: unknown) => (typeof value === 'string' ? value : '');
const lines = (value: string) => value.split('\n').map((line) => line.trim()).filter(Boolean);

export function formFromProfile(view: Pick<BuildProfileView, 'build_profile' | 'language_paths'>): ProfileForm {
  const { source = {}, paths = {} } = split(view.build_profile);
  const defines = (source.defines && typeof source.defines === 'object') ? source.defines as Record<string, unknown> : {};
  const order = Array.isArray(source.copy_search_order) ? source.copy_search_order : [];
  return {
    compiler_family: text(source.compiler_family),
    compiler_version: text(source.compiler_version),
    source_format: text(source.source_format),
    encoding: text(source.encoding),
    literal_delimiter: text(source.literal_delimiter),
    debug_mode: source.debug_mode === true,
    defines: Object.entries(defines).map(([name, value]) => `${name}=${String(value)}`).join('\n'),
    copy_search_order: order.map(String).join('\n'),
    language_paths: Object.entries(view.language_paths ?? {}).map(([prefix, label]) => `${prefix} = ${label}`).join('\n'),
    paths_json: Object.keys(paths).length ? JSON.stringify(paths, null, 2) : '',
  };
}

export type FormError = { field: 'defines' | 'language_paths' | 'paths_json'; line?: string };

/** Formular → Request-Body; Fehler nennen das Feld, die genaue Prüfung macht das Backend. */
export function profileFromForm(
  form: ProfileForm,
  previous: BuildProfileView['build_profile'],
): { body: { build_profile: StoredBuildProfile | null; language_paths: Record<string, string> | null } } | { error: FormError } {
  const kept = Object.fromEntries(Object.entries(split(previous).source ?? {}).filter(([key]) => !FORM_FIELDS.includes(key)));
  const source: ProfileFragment = { ...kept };
  for (const key of ['compiler_family', 'compiler_version', 'source_format', 'encoding', 'literal_delimiter'] as const) {
    if (form[key].trim()) source[key] = form[key].trim();
  }
  if (form.debug_mode) source.debug_mode = true;

  const defines: Record<string, string> = {};
  for (const line of lines(form.defines)) {
    const [name, ...rest] = line.split('=');
    if (!name.trim() || !rest.length) return { error: { field: 'defines', line } };
    defines[name.trim()] = rest.join('=').trim();
  }
  if (Object.keys(defines).length) source.defines = defines;
  const order = lines(form.copy_search_order);
  if (order.length) source.copy_search_order = order;

  const languagePaths: Record<string, string> = {};
  for (const line of lines(form.language_paths)) {
    const [prefix, label, extra] = line.split('=').map((part) => part.trim());
    if (!prefix || !label || extra !== undefined) return { error: { field: 'language_paths', line } };
    languagePaths[prefix] = label.toLowerCase();
  }

  let paths: Record<string, ProfileFragment> = {};
  if (form.paths_json.trim()) {
    try {
      const parsed = JSON.parse(form.paths_json);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { error: { field: 'paths_json' } };
      paths = parsed;
    } catch {
      return { error: { field: 'paths_json' } };
    }
  }

  const empty = !Object.keys(source).length && !Object.keys(paths).length;
  return {
    body: {
      build_profile: empty ? null : { source, paths },
      language_paths: Object.keys(languagePaths).length ? languagePaths : null,
    },
  };
}
