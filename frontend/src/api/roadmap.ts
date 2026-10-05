import { apiGet, apiPatch, apiPost } from "./client";

export interface RoadmapItem {
  task_id?: string; evidence_ids?: string[];
  kind: string; uid: string | null; title: string; reason: string;
  evidence: string; difficulty: number | null; done: boolean;
}
export interface RoadmapPhase { phase: number; title: string; weeks: string; items: RoadmapItem[]; }
export interface InnovationSuggestion { title: string; rationale: string; evidence: string; }
export interface RoadmapResult {
  version?: number;
  id: number | null; goal: string; phases: RoadmapPhase[];
  innovations: InnovationSuggestion[]; created_at: string | null;
}

export async function generateRoadmap(profile: {
  goal: string; known_concepts?: string[]; weekly_hours?: number;
}): Promise<RoadmapResult> {
  return apiPost<RoadmapResult>("/api/roadmap/generate", { profile });
}

export async function getRoadmap(id: number): Promise<RoadmapResult> {
  return apiGet<RoadmapResult>(`/api/roadmap/${id}`);
}

export async function listRoadmaps(): Promise<{ items: { id: number; goal: string; created_at: string }[] }> {
  return apiGet("/api/roadmap");
}

export async function updateProgress(id: number, phase: number, itemIndex: number, done: boolean): Promise<RoadmapResult> {
  return apiPatch<RoadmapResult>(`/api/roadmap/${id}/progress`, { phase, item_index: itemIndex, done });
}
