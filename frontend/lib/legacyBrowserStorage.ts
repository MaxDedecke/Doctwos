/**
 * Übergang doctus→codena (docs/UMBENENNUNG_CODENA.md): übernimmt einmalig die Browser-Einstellungen
 * aus der Zeit vor der Umbenennung (localStorage `doctus-*`, Theme-Cookie `doctus-theme`). Vorhandene
 * `codena-*`-Werte gewinnen. Läuft als Inline-Skript im <head>, also vor dem Theme-Skript und vor React.
 */
export const LEGACY_BROWSER_STORAGE_SCRIPT = `(function(){try{
var s=window.localStorage,o='doctus-',n='codena-',k=[],i;
for(i=0;i<s.length;i++){var key=s.key(i);if(key&&key.indexOf(o)===0)k.push(key);}
for(i=0;i<k.length;i++){var nk=n+k[i].slice(o.length);if(s.getItem(nk)===null)s.setItem(nk,s.getItem(k[i]));}
}catch(e){}
try{
var c=document.cookie;
if(!/(?:^|;\\s*)codena-theme=/.test(c)){var m=c.match(/(?:^|;\\s*)doctus-theme=(light|dark)(?:;|$)/);
if(m)document.cookie='codena-theme='+m[1]+'; Path=/; Max-Age=31536000; SameSite=Lax';}
}catch(e){}})();`;
