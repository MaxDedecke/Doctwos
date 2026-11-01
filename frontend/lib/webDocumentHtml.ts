import { canvasColor } from './designTokens';
import { sanitizeHtml } from './sanitize';

/** Das gemeinsame Format aller Web-Systeme (backend/services/web_documents/base.py). */
export interface WebFact { key: string; label: string; values: string[]; kind: 'text' | 'status' | 'date' }
export interface WebCrumb { title: string; url?: string | null; source_id?: number | null }
export interface WebComment { author: string; created?: string | null; body_html: string }
export interface WebAttachment { name: string; url: string; size?: number | null; mime?: string | null }
export interface WebRelated { relation: string; title: string; url: string; identifier?: string | null; status?: string | null; source_id?: number | null }
export interface WebDocumentData {
  title: string;
  url?: string | null;
  kind: string;
  identifier?: string | null;
  facts: WebFact[];
  breadcrumbs: WebCrumb[];
  body_html: string;
  comments: WebComment[];
  comments_total?: number | null;
  attachments: WebAttachment[];
  related: WebRelated[];
  extra_css: string;
  origin: 'live' | 'index';
  notice?: 'unreachable' | 'index_only' | null;
  synced_at?: string | null;
}

export const WEB_LINK_MESSAGE = 'doctus-web-link';

/** Pfade der Server-Antwort auf Bilder und Anhänge zeigen auf die API, nicht auf das Frontend. */
export const webAssetHref = (url: string, apiUrl: string) => (url.startsWith('/knowledge-sources/') ? `${apiUrl}${url}` : url);

/** Bereinigt fremdes HTML, öffnet Links getrennt und setzt die API-Adresse vor signierte Bildpfade. */
function prepareContent(dirty: string, apiUrl: string): string {
  const template = document.createElement('template');
  template.innerHTML = sanitizeHtml(dirty);
  template.content.querySelectorAll('a[href]').forEach(link => {
    if ((link.getAttribute('href') ?? '').startsWith('#')) return;
    link.setAttribute('target', '_blank');
    link.setAttribute('rel', 'noopener noreferrer');
  });
  template.content.querySelectorAll('img[src]').forEach(image => {
    image.setAttribute('src', webAssetHref(image.getAttribute('src') ?? '', apiUrl));
    image.setAttribute('loading', 'lazy');
  });
  return template.innerHTML;
}

const escapeText = (value: string) => {
  const element = document.createElement('span');
  element.textContent = value;
  return element.innerHTML;
};

function baseStyle(theme: string): string {
  // srcdoc hat ein eigenes Dokument, deshalb werden die Farben der App hier aufgelöst und als Variablen gesetzt.
  const vars = {
    fg: canvasColor('foreground'), bg: canvasColor('background'), surface: canvasColor('surface-muted'),
    border: canvasColor('border'), muted: canvasColor('foreground-muted'), accent: canvasColor('accent'),
    danger: canvasColor('danger-base'), warning: canvasColor('warning-base'), success: canvasColor('success-base'),
  };
  const declared = Object.entries(vars).map(([name, value]) => `--wd-${name}:${value}`).join(';');
  return `:root{${declared};color-scheme:${theme === 'dark' ? 'dark' : 'light'}}
html{scrollbar-width:thin;scrollbar-color:var(--wd-border) transparent}
body{margin:0;padding:16px 20px 32px;color:var(--wd-fg);background:var(--wd-bg);font:14px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;overflow-wrap:anywhere}
h1,h2,h3,h4,h5,h6{line-height:1.3;margin:1.4em 0 .5em;font-weight:700}
h1{font-size:1.5em}h2{font-size:1.3em}h3{font-size:1.15em}h4,h5,h6{font-size:1em}
main>:first-child{margin-top:0}
a{color:var(--wd-accent);text-decoration:none}a:hover{text-decoration:underline}
img{max-width:100%;height:auto;border-radius:4px}
pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.92em}
code{background:var(--wd-surface);padding:.1em .3em;border-radius:3px}
pre{background:var(--wd-surface);padding:.8em 1em;border-radius:6px;overflow-x:auto;overflow-wrap:normal}
pre code{background:transparent;padding:0}
table{border-collapse:collapse;margin:1em 0;max-width:100%}
th,td{border:1px solid var(--wd-border);padding:6px 10px;text-align:left;vertical-align:top}
th{background:var(--wd-surface);font-weight:600}
blockquote{margin:1em 0;padding:.2em 1em;border-left:3px solid var(--wd-border);color:var(--wd-muted)}
hr{border:0;border-top:1px solid var(--wd-border)}
[style*="color:"],[style*="color :"]{color:inherit!important}
[style*="background"]{background:transparent!important}
.wd-comments{margin-top:28px;border-top:1px solid var(--wd-border);padding-top:12px}
.wd-comments>h2{font-size:.8em;margin:0 0 10px;text-transform:uppercase;letter-spacing:.08em;color:var(--wd-muted)}
.wd-comment{border:1px solid var(--wd-border);border-radius:8px;padding:8px 12px;margin-bottom:10px}
.wd-comment>header{font-size:.8em;font-weight:600;color:var(--wd-muted);margin-bottom:4px}
.wd-empty{color:var(--wd-muted);font-style:italic}`;
}

// Fremdes HTML ist bereinigt und führt nichts aus; dieses Skript ist das einzige im Dokument und kennt keine Inhalte.
const LINK_SCRIPT = `<script>document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a');if(!a)return;var h=a.getAttribute('href')||'';if(h.charAt(0)==='#'){e.preventDefault();var id=h.slice(1);try{id=decodeURIComponent(id)}catch(x){}var t=document.getElementById(id)||document.getElementsByName(id)[0];if(t)t.scrollIntoView();return}if(a.dataset.doctusUrl){e.preventDefault();parent.postMessage({type:'${WEB_LINK_MESSAGE}',url:a.dataset.doctusUrl,sourceId:a.dataset.doctusSource},'*')}})</script>`;

export interface WebDocumentLabels {
  empty: string;
  comments: (shown: number, total: number) => string;
  formatDate: (value: string) => string;
}

export function buildWebDocumentHtml(doc: WebDocumentData, theme: string, apiUrl: string, labels: WebDocumentLabels): string {
  const comments = doc.comments.map(comment => {
    const meta = [comment.author, comment.created ? labels.formatDate(comment.created) : ''].filter(Boolean).map(escapeText).join(' · ');
    return `<article class="wd-comment"><header>${meta}</header>${prepareContent(comment.body_html, apiUrl)}</article>`;
  }).join('');
  const total = Math.max(doc.comments_total ?? 0, doc.comments.length);
  const body = doc.body_html.trim() ? prepareContent(doc.body_html, apiUrl) : `<p class="wd-empty">${escapeText(labels.empty)}</p>`;
  const style = `${baseStyle(theme)}\n${doc.extra_css}`.replace(/<\/style/gi, '');
  return `<!doctype html><html><head><meta charset="utf-8"><style>${style}</style></head><body><main>${body}</main>${
    comments ? `<section class="wd-comments"><h2>${escapeText(labels.comments(doc.comments.length, total))}</h2>${comments}</section>` : ''
  }${LINK_SCRIPT}</body></html>`;
}

export function addWebAnchorScroll(html: string, anchor: string | null | undefined) {
  if (!anchor) return html;
  const safeAnchor = JSON.stringify(anchor.replace(/^#/, '')).replace(/</g, '\\u003c');
  const script = `<script>(()=>{const id=${safeAnchor};let decoded=id;try{decoded=decodeURIComponent(id)}catch{};const jump=()=>{const target=document.getElementById(decoded)||document.getElementsByName(decoded)[0];if(target)target.scrollIntoView({block:'start'})};requestAnimationFrame(jump);window.addEventListener('load',jump,{once:true})})();</script>`;
  return /<\/body\s*>/i.test(html)
    ? html.replace(/<\/body\s*>/i, `${script}</body>`)
    : `${html}${script}`;
}
