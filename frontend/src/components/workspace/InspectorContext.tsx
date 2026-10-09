import { createContext, useContext } from "react";
import type { Reference, Resource } from "../../api/assistant";
export interface InspectorAPI { available?: boolean; inspect: (reference: Reference, selection?: Record<string,string|null>) => void; openResource: (resource: Resource) => void; refresh: () => void }
export const InspectorContext = createContext<InspectorAPI>({ available: false, inspect: () => undefined, openResource: () => undefined, refresh: () => undefined });
export const useInspector = () => useContext(InspectorContext);
