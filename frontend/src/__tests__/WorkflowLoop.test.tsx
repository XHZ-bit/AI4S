import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import RoadmapReplan from "../components/RoadmapReplan";
import { commitReplan, previewReplan, type RoadmapResult } from "../api/roadmap";

vi.mock("../api/roadmap", () => ({ previewReplan: vi.fn(), commitReplan: vi.fn() }));

test("route adjustment requires review before saving a new version", async () => {
  const route: RoadmapResult = { id: 7, version: 2, goal: "target", phases: [], innovations: [], created_at: null };
  const next: RoadmapResult = { ...route, id: 8, version: 1, parent_id: 7 };
  vi.mocked(previewReplan).mockResolvedValue({
    roadmap: next, input_fingerprint: "f".repeat(64),
    schedule: { weekly_hours: 3, estimated_minutes: 45, unscheduled_count: 0 },
    confirmed_concepts: ["concept:basics"], removed_phase_count: 1,
  });
  vi.mocked(commitReplan).mockResolvedValue(next);
  const onSaved = vi.fn();
  render(<MemoryRouter><RoadmapReplan route={route} onSaved={onSaved} /></MemoryRouter>);
  expect(commitReplan).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "预览调整" }));
  await screen.findByText(/每周 3 小时/);
  expect(commitReplan).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认生成新路线版本" }));
  await waitFor(() => expect(commitReplan).toHaveBeenCalledWith(7, 2, "f".repeat(64)));
  expect(onSaved).toHaveBeenCalledWith(next);
});
