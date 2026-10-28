import { canvasColor } from './designTokens';

export function addWebOriginTheme(html: string, theme: string, sourceType: string | null | undefined) {
  if (sourceType?.toLowerCase() !== 'jira') return html;
  // srcdoc has its own document, so resolve the app's tokens before inserting CSS.
  const foreground = canvasColor('foreground');
  const background = canvasColor('background');
  const link = canvasColor('accent');
  const codeBackground = canvasColor('surface-muted');
  const style = `<style>html,body{color-scheme:${theme === 'dark' ? 'dark' : 'light'};color:${foreground}!important;background:${background}!important}body{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6;margin:0;padding:24px}p,li,blockquote,td,th{color:${foreground}!important}a{color:${link}!important}pre,code{color:${foreground}!important;background:${codeBackground}!important}img{max-width:100%;height:auto}table{border-collapse:collapse;max-width:100%}</style>`;
  return `${style}${html}`;
}

export function addWebAnchorScroll(html: string, anchor: string | null | undefined) {
  if (!anchor) return html;
  const safeAnchor = JSON.stringify(anchor.replace(/^#/, '')).replace(/</g, '\\u003c');
  const script = `<script>(()=>{const id=${safeAnchor};let decoded=id;try{decoded=decodeURIComponent(id)}catch{};const jump=()=>{const target=document.getElementById(decoded)||document.getElementsByName(decoded)[0];if(target)target.scrollIntoView({block:'start'})};requestAnimationFrame(jump);window.addEventListener('load',jump,{once:true})})();</script>`;
  return /<\/body\s*>/i.test(html)
    ? html.replace(/<\/body\s*>/i, `${script}</body>`)
    : `${html}${script}`;
}
