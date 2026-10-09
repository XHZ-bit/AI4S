import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import AutomaticRoadmapPreview from "../components/AutomaticRoadmapPreview";

const api = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("../api/client", () => api);

test("machine checked route remains a read-only preview", async () => {
  api.apiGet.mockResolvedValue({ items: [{ uid: "concept:target", name: "Target", type: "concept" }] });
  api.apiPost.mockResolvedValue({
    evidence_level: "machine_checked_preview", checked_relations: 2,
    notice: "机器核查结果，不是正式路线。",
    schedule: { estimated_minutes: 20, unscheduled_count: 0 },
    route: { phases: [{ phase: 1, title: "Target", weeks: "第 1 周", items: [
      { kind: "paper", uid: "p1", title: "Paper One", reason: "source evidence", evidence_ids: ["e1"] },
    ] }] },
  });
  render(<MemoryRouter><AutomaticRoadmapPreview /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("候选路线目标描述"), { target: { value: "Learn Target" } });
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "机器核查目标实体" }));
  fireEvent.click(await screen.findByText("Target · concept"));
  fireEvent.click(screen.getByRole("button", { name: "生成候选预览" }));
  expect(await screen.findByText("Paper One")).toBeTruthy();
  expect(screen.getByText("机器核查结果，不是正式路线。")).toBeTruthy();
  await waitFor(() => expect(api.apiPost).toHaveBeenCalledTimes(1));
  expect(api.apiPost.mock.calls[0][0]).toBe("/api/roadmap/auto-preview");
});
