import { createContext, useContext } from "react";
import type { Reference, Resource } from "../../api/assistant";
import type { SourceSelection } from "../../api/workContext";
export interface InspectorAPI { available?: boolean; selection?: SourceSelection; restoreSelection?: (selection:SourceSelection)=>void; inspect: (reference: Reference, selection?: Record<string,string|null>) => void; openResource: (resource: Resource) => void; refresh: () => void; openSelection?: (selection: SourceSelection, panel: 'tutor'|'notes') => void }
export const InspectorContext = createContext<InspectorAPI>({ available: false, inspect: () => undefined, openResource: () => undefined, refresh: () => undefined });
export const useInspector = () => useContext(InspectorContext);
