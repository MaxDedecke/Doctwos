import { useSyncExternalStore } from 'react';

function subscribe(changed: () => void) {
  const observer = new MutationObserver(changed);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style'] });
  return () => observer.disconnect();
}

const snapshot = () => `${document.documentElement.className}|${document.documentElement.style.cssText}`;
const serverSnapshot = () => '';

/** Theme CSS is applied by the parent effect, after the child's render-time palette snapshot. */
export function useGraphStyleRevision() {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
