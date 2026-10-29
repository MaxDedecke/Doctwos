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

  interface RadialForce<Node> {
    (alpha: number): void;
    strength(): (node: Node, index: number, nodes: Node[]) => number;
    strength(value: number | ((node: Node, index: number, nodes: Node[]) => number)): this;
  }

  export function forceCollide<Node = unknown>(radius?: number | ((node: Node, index: number, nodes: Node[]) => number)): CollisionForce<Node>;
  export function forceManyBody<Node = unknown>(): ManyBodyForce<Node>;
  export function forceRadial<Node = unknown>(radius: number | ((node: Node, index: number, nodes: Node[]) => number), x?: number, y?: number, z?: number): RadialForce<Node>;

  interface PositionForce<Node> {
    (alpha: number): void;
    strength(value: number | ((node: Node, index: number, nodes: Node[]) => number)): this;
  }
  export function forceX<Node = unknown>(x: number | ((node: Node, index: number, nodes: Node[]) => number)): PositionForce<Node>;
  export function forceY<Node = unknown>(y: number | ((node: Node, index: number, nodes: Node[]) => number)): PositionForce<Node>;

  interface Simulation<Node> {
    stop(): this;
    tick(iterations?: number): this;
    alphaDecay(value: number): this;
    velocityDecay(value: number): this;
    force(name: string, force: unknown): this;
  }
  interface LinkForce {
    id<Node>(accessor: (node: Node) => string): this;
    distance<Edge>(accessor: (edge: Edge) => number): this;
    strength<Edge>(value: number | ((edge: Edge) => number)): this;
  }
  export function forceSimulation<Node>(nodes: Node[], dimensions?: number): Simulation<Node>;
  export function forceLink(links: { source: string; target: string }[]): LinkForce;
}
