const vscode = require('vscode');
const path = require('node:path');
const fs = require('node:fs/promises');

const cache = new Map();

function config(document) {
  const folder = vscode.workspace.getWorkspaceFolder(document.uri);
  if (!folder || document.uri.scheme !== 'file') return null;
  const settings = vscode.workspace.getConfiguration('doctus', document.uri);
  const projectId = settings.get('projectId');
  const sourceId = settings.get('sourceId');
  if (!Number.isSafeInteger(projectId) || projectId <= 0 || !Number.isSafeInteger(sourceId) || sourceId <= 0) return null;
  const root = path.resolve(folder.uri.fsPath, settings.get('repositoryRoot') || '.');
  const relative = path.relative(root, document.uri.fsPath).split(path.sep).join('/');
  if (!relative || relative === '..' || relative.startsWith('../') || path.isAbsolute(relative)) return null;
  return {
    apiUrl: settings.get('apiUrl').replace(/\/$/, ''),
    webUrl: settings.get('webUrl').replace(/\/$/, ''),
    projectId, sourceId, path: relative, variantKey: settings.get('variantKey') || ''
  };
}

function graphUrl(settings, line) {
  const url = new URL(settings.webUrl);
  url.searchParams.set('ide_project', String(settings.projectId));
  url.searchParams.set('ide_source', String(settings.sourceId));
  url.searchParams.set('ide_path', settings.path);
  url.searchParams.set('ide_line', String(line));
  if (settings.variantKey) url.searchParams.set('ide_variant', settings.variantKey);
  return url.toString();
}

async function annotations(document, context) {
  const settings = config(document);
  if (!settings) return null;
  const token = await context.secrets.get('doctus.personalToken');
  if (!token) return null;
  const key = `${document.uri.toString()}|${JSON.stringify(settings)}`;
  const cached = cache.get(key);
  if (cached && Date.now() - cached.time < 30000) return { settings, references: cached.references };
  const url = new URL(`${settings.apiUrl}/ide/file`);
  url.searchParams.set('project_id', String(settings.projectId));
  url.searchParams.set('source_id', String(settings.sourceId));
  url.searchParams.set('path', settings.path);
  if (settings.variantKey) url.searchParams.set('variant_key', settings.variantKey);
  const response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (response.status === 404) return { settings, references: [] };
  if (!response.ok) throw new Error(`Doctus HTTP ${response.status}`);
  const data = await response.json();
  cache.set(key, { time: Date.now(), references: data.references });
  return { settings, references: data.references };
}

function label(ref) {
  const destination = ref.target ? `${ref.target.file_path}:${ref.target.start_line || 1}` : ref.resolution;
  return `Doctus: ${ref.type} ${ref.name} → ${destination}`;
}

function markdownText(value) {
  return String(value ?? '').replace(/[\\`*_{}\[\]()#+.!|>-]/g, '\\$&');
}

function referenceRange(document, ref) {
  const line = ref.line - 1;
  if (line < 0 || line >= document.lineCount) return null;
  const text = document.lineAt(line).text;
  const nameIndex = text.toLocaleLowerCase().indexOf(String(ref.name).toLocaleLowerCase());
  const keywordIndex = text.toLocaleLowerCase().indexOf(ref.type.toLocaleLowerCase());
  const start = nameIndex >= 0 ? nameIndex : Math.max(0, keywordIndex);
  return new vscode.Range(line, start, line, start + (nameIndex >= 0 ? ref.name.length : ref.type.length));
}

async function activate(context) {
  // One-time migration hook for an administrator-provisioned token. The token
  // is moved immediately into VS Code's encrypted SecretStorage and the staged
  // plaintext is removed before any providers are registered.
  const tokenHandoff = path.join(context.globalStorageUri.fsPath, 'doctus-token-once');
  try {
    const token = (await fs.readFile(tokenHandoff, 'utf8')).trim();
    if (!token.startsWith('dct_mcp_')) throw new Error('Invalid Doctus token handoff');
    await context.secrets.store('doctus.personalToken', token);
    await fs.unlink(tokenHandoff);
    cache.clear();
  } catch (error) {
    if (error.code !== 'ENOENT') console.error('Doctus token handoff failed:', error);
  }
  context.subscriptions.push(vscode.commands.registerCommand('doctus.setToken', async () => {
    const token = await vscode.window.showInputBox({ prompt: 'Personal Doctus token (from Settings → IDE / MCP)', password: true, ignoreFocusOut: true });
    if (token !== undefined) {
      await context.secrets.store('doctus.personalToken', token.trim());
      cache.clear();
      vscode.window.showInformationMessage('Doctus token saved.');
    }
  }));
  context.subscriptions.push(vscode.commands.registerCommand('doctus.openGraph', async (settings, line) => {
    if (!settings || !line) {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      settings = config(editor.document);
      line = editor.selection.active.line + 1;
    }
    if (!settings) {
      vscode.window.showWarningMessage('Set Doctus projectId and sourceId for this workspace.');
      return;
    }
    await vscode.env.openExternal(vscode.Uri.parse(graphUrl(settings, line)));
  }));
  const selector = { scheme: 'file' };
  context.subscriptions.push(vscode.languages.registerCodeLensProvider(selector, {
    async provideCodeLenses(document) {
      try {
        const result = await annotations(document, context);
        if (!result) return [];
        return result.references.filter(ref => ref.line).map(ref => {
          const range = referenceRange(document, ref);
          return range && new vscode.CodeLens(range, {
            title: label(ref), command: 'doctus.openGraph', arguments: [result.settings, ref.line]
          });
        }).filter(Boolean);
      } catch (error) {
        console.error('Doctus CodeLens:', error);
        return [];
      }
    }
  }));
  context.subscriptions.push(vscode.languages.registerHoverProvider(selector, {
    async provideHover(document, position) {
      try {
        const result = await annotations(document, context);
        const ref = result?.references.find(item => {
          const range = item.line && referenceRange(document, item);
          return range && range.contains(position);
        });
        if (!ref) return null;
        const body = new vscode.MarkdownString(`**${markdownText(ref.type)} ${markdownText(ref.name)}** · ${markdownText(ref.resolution)}\n\n` +
          (ref.target ? `Target: ${markdownText(ref.target.file_path)}:${ref.target.start_line || 1}\n\n` : '') +
          `[Open in Doctus graph](${graphUrl(result.settings, ref.line)})`);
        return new vscode.Hover(body, referenceRange(document, ref));
      } catch (error) {
        console.error('Doctus hover:', error);
        return null;
      }
    }
  }));
  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(() => cache.clear()));
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
    if (event.affectsConfiguration('doctus')) cache.clear();
  }));
}

module.exports = { activate, deactivate() {} };
