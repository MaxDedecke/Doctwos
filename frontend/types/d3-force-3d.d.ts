// Local declarations for the force factories used by KnowledgeGraphView.
// Signatures follow the installed d3-force-3d implementation in src/.
declare module 'd3-force-3d' {
  interface CollisionForce<Node> {
    (): void;
    radius(): (node: Node, index: number, nodes: Node[]) => number;
    radius(value: number | ((node: Node, index: number, nodes: Node[]) => number)): this;
    iterations(): number;
    iterations(value: number): this;
  }

  interface ManyBodyForce<Node> {
    (alpha: number): void;
    strength(): (node: Node, index: number, nodes: Node[]) => number;
    strength(value: number | ((node: Node, index: number, nodes: Node[]) => number)): this;
    distanceMax(): number;
    distanceMax(value: number): this;
  }

  export function forceCollide<Node = unknown>(radius?: number | ((node: Node, index: number, nodes: Node[]) => number)): CollisionForce<Node>;
  export function forceManyBody<Node = unknown>(): ManyBodyForce<Node>;
}
