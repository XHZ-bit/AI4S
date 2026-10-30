import { createContext, useContext, type ReactNode } from "react";

export type AccessMode = "local" | "multiuser";
import type {SessionUser} from "../api/session";

const AccessModeContext = createContext<AccessMode>("local");
const AccountContext=createContext<SessionUser|null>(null);
export const useCurrentAccount=()=>useContext(AccountContext);

/** Shares the mode already verified by SessionGate; this is a UI hint, not authorization. */
export function AccessModeProvider({ mode, children,user=null }: { mode: AccessMode; children: ReactNode;user?:SessionUser|null }) {
  return <AccessModeContext.Provider value={mode}><AccountContext.Provider value={user}>{children}</AccountContext.Provider></AccessModeContext.Provider>;
}

export function useAccessMode(): AccessMode {
  return useContext(AccessModeContext);
}
