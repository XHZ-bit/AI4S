import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import PersonalizedRoadmapDemo from "../pages/PersonalizedRoadmapDemo";

test("the complete demo is available immediately and changes prerequisites with the learner", () => {
  render(<MemoryRouter><PersonalizedRoadmapDemo/></MemoryRouter>);
  expect(screen.getByRole("heading", {name: "理解扩散模型的训练与采样"})).toBeTruthy();
  expect(screen.queryByRole("heading", {name: "建立机器人模仿学习的问题框架"})).toBeNull();
  fireEvent.click(within(screen.getByRole("navigation", {name: "示例学习者"})).getByRole("button", {name: /许同学/}));
  expect(screen.getByRole("heading", {name: "建立机器人模仿学习的问题框架"})).toBeTruthy();
  expect(screen.queryByRole("heading", {name: "理解扩散模型的训练与采样"})).toBeNull();
  fireEvent.click(screen.getByRole("tab", {name: "模拟学习过程"}));
  expect(screen.getByText("生成的动作序列平滑，就代表策略更好吗？", {exact: false})).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", {name: "完整产出报告"}));
  expect(screen.getByRole("button", {name: "导出完整案例"})).toBeTruthy();
  expect(screen.getByRole("heading", {name: "学习反思"})).toBeTruthy();
});
