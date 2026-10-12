import { createContext, useContext, type ReactNode } from "react";

export type AdminTab = "models" | "embedding" | "retrieval" | "users" | "connections" | "tools" | "auth";

// Querverweise zwischen den Admin-Bereichen (z. B. "Verbindungen" auf der Modelle-Seite).
export const AdminNav = createContext<((tab: AdminTab) => void) | null>(null);

export function AdminLink({ tab, children }: { tab: AdminTab; children: ReactNode }) {
  const go = useContext(AdminNav);
  return (
    <button type="button" onClick={() => go?.(tab)} className="underline underline-offset-2">
      {children}
    </button>
  );
}
