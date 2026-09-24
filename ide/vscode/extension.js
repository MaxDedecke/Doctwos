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
    projectId, sourceId, path: relative, repositoryRoot: root,
    variantKey: settings.get('variantKey') || ''
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

function utf16Offset(text, codePointColumn) {
  const points = Array.from(text);
  return codePointColumn <= points.length ? points.slice(0, codePointColumn).join('').length : null;
}

function referenceRange(document, ref, allowLineFallback = false) {
  const line = ref.line - 1;
  if (line < 0 || line >= document.lineCount) return null;
  const text = document.lineAt(line).text;
  if (Number.isSafeInteger(ref.start_column) && Number.isSafeInteger(ref.end_column) &&
      ref.start_column >= 0 && ref.end_column > ref.start_column) {
    const start = utf16Offset(text, ref.start_column);
    const end = utf16Offset(text, ref.end_column);
    if (start !== null && end !== null &&
        (!ref.symbol_name || text.slice(start, end) === ref.symbol_name)) {
      return new vscode.Range(line, start, line, end);
    }
  }
  const name = String(ref.symbol_name || ref.name || '');
  const haystack = text.toLowerCase();
  const needle = name.toLowerCase();
  const first = needle ? haystack.indexOf(needle) : -1;
  if (first >= 0 && haystack.indexOf(needle, first + 1) < 0) {
    return new vscode.Range(line, first, line, first + name.length);
  }
  return allowLineFallback ? new vscode.Range(line, 0, line, 0) : null;
}

async function openTarget(settings, ref) {
  const target = ref?.target;
  if (!target || ref.resolution !== 'resolved' || target.source_id !== settings.sourceId ||
      typeof target.file_path !== 'string') {
    await vscode.env.openExternal(vscode.Uri.parse(graphUrl(settings, ref.line)));
    return;
  }
  const folder = vscode.workspace.workspaceFolders?.find(item => {
    const root = path.resolve(item.uri.fsPath, vscode.workspace.getConfiguration('doctus', item.uri).get('repositoryRoot') || '.');
    return root === settings.repositoryRoot;
  });
  if (!folder) {
    await vscode.env.openExternal(vscode.Uri.parse(graphUrl(settings, ref.line)));
    return;
  }
  const root = settings.repositoryRoot;
  const absolute = path.resolve(root, target.file_path);
  const relative = path.relative(root, absolute);
  if (!relative || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    await vscode.env.openExternal(vscode.Uri.parse(graphUrl(settings, ref.line)));
    return;
  }
  try {
    const realRoot = await fs.realpath(root);
    const realTarget = await fs.realpath(absolute);
    const realRelative = path.relative(realRoot, realTarget);
    if (!realRelative || realRelative === '..' || realRelative.startsWith(`..${path.sep}`) || path.isAbsolute(realRelative)) {
      throw new Error('Target outside repository');
    }
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(absolute));
    const line = Math.max(0, Math.min(document.lineCount - 1, (target.start_line || 1) - 1));
    await vscode.window.showTextDocument(document, { selection: new vscode.Range(line, 0, line, 0) });
  } catch {
    await vscode.env.openExternal(vscode.Uri.parse(graphUrl(settings, ref.line)));
  }
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
  context.subscriptions.push(vscode.commands.registerCommand('doctus.openTarget', openTarget));
  const selector = { scheme: 'file' };
  context.subscriptions.push(vscode.languages.registerCodeLensProvider(selector, {
    async provideCodeLenses(document) {
      try {
        const result = await annotations(document, context);
        if (!result) return [];
        return result.references.filter(ref => ref.line).map(ref => {
          const range = referenceRange(document, ref, true);
          return range && new vscode.CodeLens(range, {
            title: label(ref),
            command: ref.target && ref.resolution === 'resolved' ? 'doctus.openTarget' : 'doctus.openGraph',
            arguments: ref.target && ref.resolution === 'resolved'
              ? [result.settings, ref] : [result.settings, ref.line]
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
          (ref.resolution_reason ? `Resolution: ${markdownText(ref.resolution_reason)}\n\n` : '') +
          (ref.dispatch_scope ? `Dispatch: ${markdownText(ref.dispatch_scope)}\n\n` : '') +
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
