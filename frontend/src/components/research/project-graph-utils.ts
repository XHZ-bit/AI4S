import type { GraphEdge, GraphNode } from "../../api/project-types";

export type ProjectGraphMode = "overview" | "evidence" | "method" | "impact";

export const nodeTypeLabels: Record<string, string> = {
  project: "课题",
  paper: "论文",
  document: "文档",
  method: "方法",
  experiment_setting: "实验设置",
  measurement: "测量",
  evidence: "证据",
  decision: "决策",
  plan: "方案",
};

export const nodeTypeColors: Record<string, string> = {
  project: "#1d39c4", paper: "#08979c", document: "#13c2c2", method: "#1677ff",
  experiment_setting: "#722ed1", measurement: "#eb2f96", evidence: "#d48806",
  decision: "#389e0d", plan: "#cf1322",
};

const endpoints = (edge: GraphEdge) => [edge.source_id, edge.target_id] as const;

export function adjacency(edges: GraphEdge[]) {
  const map = new Map<string, Set<string>>();
  edges.forEach(edge => {
    const [source, target] = endpoints(edge);
    if (!map.has(source)) map.set(source, new Set());
    if (!map.has(target)) map.set(target, new Set());
    map.get(source)!.add(target); map.get(target)!.add(source);
  });
  return map;
}

export function neighborhood(edges: GraphEdge[], starts: string[], depth: number, limit = 80) {
  const graph = adjacency(edges);
  const seen = new Set(starts);
  let frontier = starts;
  for (let level = 0; level < depth && frontier.length && seen.size < limit; level += 1) {
    const next: string[] = [];
    frontier.forEach(id => graph.get(id)?.forEach(neighbor => {
      if (seen.size < limit && !seen.has(neighbor)) { seen.add(neighbor); next.push(neighbor); }
    }));
    frontier = next;
  }
  return seen;
}

export function shortestPath(edges: GraphEdge[], start: string, target: string, maxDepth = 6): string[] | null {
  if (start === target) return [start];
  const graph = adjacency(edges);
  const queue: { id: string; path: string[] }[] = [{ id: start, path: [start] }];
  const seen = new Set([start]);
  while (queue.length) {
    const current = queue.shift()!;
    if (current.path.length > maxDepth) continue;
    for (const neighbor of graph.get(current.id) ?? []) {
      if (seen.has(neighbor)) continue;
      const path = [...current.path, neighbor];
      if (neighbor === target) return path;
      seen.add(neighbor); queue.push({ id: neighbor, path });
    }
  }
  return null;
}

export function evidencePaths(nodes: GraphNode[], edges: GraphEdge[], focusId: string) {
  return nodes.filter(node => node.kind === "evidence").map(node => shortestPath(edges, focusId, node.id)).filter((path): path is string[] => !!path);
}

export function impactPaths(nodes: GraphNode[], edges: GraphEdge[], evidenceId: string) {
  return nodes.filter(node => ["decision", "plan"].includes(node.kind)).map(node => shortestPath(edges, evidenceId, node.id)).filter((path): path is string[] => !!path);
}

export function initialFocus(nodes: GraphNode[], requested?: string | null) {
  if (requested && nodes.some(node => node.id === requested)) return requested;
  return nodes.find(node => node.kind === "plan")?.id
    ?? nodes.find(node => node.kind === "decision")?.id
    ?? nodes.find(node => node.kind === "method")?.id
    ?? nodes[0]?.id
    ?? null;
}

export function graphView(nodes: GraphNode[], edges: GraphEdge[], mode: ProjectGraphMode, focusId: string | null, expanded: Set<string>) {
  if (!focusId) return { nodeIds: new Set<string>(), highlighted: new Set<string>(), paths: [] as string[][] };
  let paths: string[][] = [];
  let nodeIds: Set<string>;
  if (mode === "evidence") {
    paths = evidencePaths(nodes, edges, focusId);
    nodeIds = new Set(paths.flat());
  } else if (mode === "impact") {
    paths = impactPaths(nodes, edges, focusId);
    nodeIds = new Set(paths.flat());
  } else {
    nodeIds = neighborhood(edges, [focusId], mode === "method" ? 2 : 1);
  }
  expanded.forEach(id => neighborhood(edges, [id], 1).forEach(item => nodeIds.add(item)));
  nodeIds.add(focusId);
  return { nodeIds, highlighted: new Set(paths.flat()), paths };
}
