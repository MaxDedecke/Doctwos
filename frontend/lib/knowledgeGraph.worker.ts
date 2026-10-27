import { simulateGraph } from './knowledgeGraphSimulation';
import type { LayoutRequest } from './knowledgeGraphLayout';

let cancel: (() => void) | undefined;
self.onmessage = (event: MessageEvent<LayoutRequest>) => {
  cancel?.();
  cancel = simulateGraph(event.data, result => self.postMessage(result));
};
