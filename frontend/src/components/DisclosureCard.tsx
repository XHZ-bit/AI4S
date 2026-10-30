import { useId, useState, type ReactNode } from "react";
import { Button, Card } from "antd";

export default function DisclosureCard({title, children, storageKey, defaultCollapsed = false}: {
  title: string; children: ReactNode; storageKey: string; defaultCollapsed?: boolean;
}) {
  const contentId = useId();
  const [collapsed, setCollapsed] = useState(() => {
    try { const value = localStorage.getItem(storageKey); return value === null ? defaultCollapsed : value === "true"; }
    catch { return defaultCollapsed; }
  });
  function toggle() {
    setCollapsed(previous => {
      const next = !previous;
      try { localStorage.setItem(storageKey, String(next)); } catch { /* Session state remains usable. */ }
      return next;
    });
  }
  return <Card className={`atlas-disclosure-card${collapsed ? " is-collapsed" : ""}`} title={title}
    extra={<Button size="small" type="text" aria-label={`${collapsed ? "展开" : "收起"}${title}`} aria-expanded={!collapsed} aria-controls={contentId} onClick={toggle}>{collapsed ? "展开" : "收起"}</Button>}>
    <div id={contentId} hidden={collapsed}>{children}</div>
  </Card>;
}
