"use client";
import React from 'react';

const BRAND_COLORS = ['#d60055', '#7047eb', '#0064d2'];
const CLUSTER_MS = 7000;
const SPAWN_EVERY_MS = 1300;
const MAX_CLUSTERS = 7;
const EDGE_STEP_MS = 420;
const EDGE_GROW_MS = 600;
const NODE_FADE_IN_MS = 350;
const FADE_OUT_MS = 1600;

interface Node { x: number; y: number; color: string; appearAt: number }
interface Edge { a: number; b: number; startAt: number }
interface Cluster { t0: number; nodes: Node[]; edges: Edge[] }

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Würfelt einen Knotenhaufen, der den Bereich von Logo und Formular in der Mitte ausspart. */
function buildCluster(width: number, height: number, now: number): Cluster {
  const keepOutX = Math.min(width * 0.45, 250);
  const keepOutY = Math.min(height * 0.46, 360);
  const inKeepOut = (x: number, y: number) =>
    Math.abs(x - width / 2) < keepOutX && Math.abs(y - height / 2) < keepOutY;

  const cx = width * (0.12 + Math.random() * 0.76);
  const cy = height * (0.12 + Math.random() * 0.76);
  const radius = Math.min(width, height) * (0.14 + Math.random() * 0.1);
  const count = 6 + Math.floor(Math.random() * 3);
  const points: { x: number; y: number }[] = [];
  for (let attempt = 0; attempt < count * 12 && points.length < count; attempt++) {
    const angle = Math.random() * Math.PI * 2;
    const dist = Math.sqrt(Math.random()) * radius;
    const x = Math.min(width - 12, Math.max(12, cx + Math.cos(angle) * dist));
    const y = Math.min(height - 12, Math.max(12, cy + Math.sin(angle) * dist));
    if (inKeepOut(x, y)) continue;
    // Mindestabstand, damit Knoten nicht aufeinander sitzen.
    if (points.some(p => Math.hypot(p.x - x, p.y - y) < 36)) continue;
    points.push({ x, y });
  }

  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const distance = (i: number, j: number) => Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y);
  points.forEach((p, i) => {
    const color = BRAND_COLORS[Math.floor(Math.random() * BRAND_COLORS.length)];
    if (i === 0) {
      nodes.push({ ...p, color, appearAt: 0 });
      return;
    }
    // Jeder neue Knoten hängt sich per Kante an den nächsten bereits vorhandenen
    // an; die Kante wächst auf ihn zu, er erscheint beim Eintreffen.
    const startAt = i * EDGE_STEP_MS;
    const ranked = nodes.map((_, j) => j).sort((a, b) => distance(i, a) - distance(i, b));
    edges.push({ a: ranked[0], b: i, startAt });
    if (ranked.length > 2 && Math.random() < 0.6) edges.push({ a: ranked[1], b: i, startAt: startAt + 200 });
    nodes.push({ ...p, color, appearAt: startAt + EDGE_GROW_MS });
  });
  return { t0: now, nodes, edges };
}

function drawCluster(ctx: CanvasRenderingContext2D, cluster: Cluster, now: number, isDark: boolean) {
  const age = now - cluster.t0;
  const fadeOut = Math.min(1, Math.max(0, (CLUSTER_MS - age) / FADE_OUT_MS));
  if (fadeOut <= 0) return;

  ctx.lineWidth = 1.25;
  for (const edge of cluster.edges) {
    const progress = Math.min(1, Math.max(0, (age - edge.startAt) / EDGE_GROW_MS));
    if (progress <= 0) continue;
    const from = cluster.nodes[edge.a];
    const to = cluster.nodes[edge.b];
    const x = from.x + (to.x - from.x) * progress;
    const y = from.y + (to.y - from.y) * progress;
    const gradient = ctx.createLinearGradient(from.x, from.y, to.x, to.y);
    gradient.addColorStop(0, from.color);
    gradient.addColorStop(1, to.color);
    ctx.globalAlpha = 0.55 * fadeOut;
    ctx.strokeStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(x, y);
    ctx.stroke();
  }

  for (const node of cluster.nodes) {
    const appear = Math.min(1, Math.max(0, (age - node.appearAt) / NODE_FADE_IN_MS));
    if (appear <= 0) continue;
    ctx.globalAlpha = fadeOut * appear;
    // Weicher Hof + fester Kern; leichtes Aufploppen beim Erscheinen.
    const scale = 0.6 + 0.4 * appear;
    ctx.fillStyle = node.color;
    ctx.globalAlpha = 0.16 * fadeOut * appear;
    ctx.beginPath();
    ctx.arc(node.x, node.y, 10 * scale, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = fadeOut * appear;
    ctx.beginPath();
    ctx.arc(node.x, node.y, 3.5 * scale, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = isDark ? '#09090b' : '#ffffff';
    ctx.beginPath();
    ctx.arc(node.x, node.y, 1.4 * scale, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

/** Endlosschleife: Knoten verbinden sich über Kanten und blenden wieder aus. */
export function NetworkLoopCanvas({ isDark, className }: { isDark: boolean; className?: string }) {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let width = 0;
    let height = 0;
    let frame = 0;
    let clusters: Cluster[] = [];
    let lastSpawn = 0;
    const reduced = prefersReducedMotion();

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    observer?.observe(canvas);

    if (reduced) {
      // Ein ruhiges Standbild statt Animation.
      const still = buildCluster(width, height, 0);
      drawCluster(ctx, still, CLUSTER_MS - FADE_OUT_MS, isDark);
      return () => observer?.disconnect();
    }

    const tick = (now: number) => {
      if (width > 0 && height > 0) {
        // Sofort befüllen: die ersten Haufen starten schon mitten in ihrem Ablauf.
        if (lastSpawn === 0) {
          for (let i = 0; i < 4; i++) {
            clusters.push(buildCluster(width, height, now - 500 - i * 1400 - Math.random() * 600));
          }
          lastSpawn = now;
        }
        clusters = clusters.filter(c => now - c.t0 < CLUSTER_MS);
        if (clusters.length < MAX_CLUSTERS && now - lastSpawn >= SPAWN_EVERY_MS) {
          clusters.push(buildCluster(width, height, now));
          lastSpawn = now;
        }
        ctx.clearRect(0, 0, width, height);
        for (const cluster of clusters) drawCluster(ctx, cluster, now, isDark);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [isDark]);

  return <canvas ref={canvasRef} aria-hidden="true" className={className} />;
}
