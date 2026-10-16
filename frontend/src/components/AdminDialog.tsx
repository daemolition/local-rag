import { useEffect, useState, type ReactNode } from "react";
import { Cpu, KeyRound, Layers, Plug, SlidersHorizontal, Users, Wrench, ScrollText,
} from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { AdminAuthPage } from "@/pages/AdminAuthPage";
import { AdminAuditPage } from "@/pages/AdminAuditPage";

import { AdminConnectionsPage } from "@/pages/AdminConnectionsPage";
import { AdminEmbeddingPage } from "@/pages/AdminEmbeddingPage";
import { AdminModelsPage } from "@/pages/AdminModelsPage";
import { AdminRetrievalPage } from "@/pages/AdminRetrievalPage";
import { AdminToolsPage } from "@/pages/AdminToolsPage";
import { AdminUsersPage } from "@/pages/AdminUsersPage";
import { AdminNav, type AdminTab } from "@/components/AdminNav";
import { cn } from "@/lib/utils";

export type { AdminTab };

const TABS: { id: AdminTab; label: string; icon: ReactNode; page: ReactNode }[] = [
  { id: "models", label: "Modelle", icon: <Cpu className="size-4" />, page: <AdminModelsPage /> },
  { id: "embedding", label: "Einlesen & Modelle", icon: <Layers className="size-4" />, page: <AdminEmbeddingPage /> },
  { id: "retrieval", label: "Retrieval", icon: <SlidersHorizontal className="size-4" />, page: <AdminRetrievalPage /> },
  { id: "tools", label: "Tools", icon: <Wrench className="size-4" />, page: <AdminToolsPage /> },
  { id: "users", label: "Benutzer & Gruppen", icon: <Users className="size-4" />, page: <AdminUsersPage /> },
  { id: "auth", label: "Authentifizierung", icon: <KeyRound className="size-4" />, page: <AdminAuthPage /> },
  { id: "audit", label: "Protokoll", icon: <ScrollText className="size-4" />, page: <AdminAuditPage /> },
  { id: "connections", label: "Verbindungen", icon: <Plug className="size-4" />, page: <AdminConnectionsPage /> },
];

interface AdminDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tab: AdminTab;
  onTabChange: (tab: AdminTab) => void;
}

/** Alle Admin-Bereiche in einem Dialog statt in der Seitenleiste. */
export function AdminDialog({ open, onOpenChange, tab, onTabChange }: AdminDialogProps) {
  // Besuchte Reiter bleiben gemountet (nur ausgeblendet), damit Eingaben beim Wechseln nicht verloren gehen.
  const [visited, setVisited] = useState<AdminTab[]>([tab]);
  useEffect(() => {
    setVisited((v) => (v.includes(tab) ? v : [...v, tab]));
  }, [tab]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[88vh] max-w-[calc(100%-2rem)] flex-col gap-0 overflow-hidden p-0 sm:max-w-6xl">
        <DialogTitle className="sr-only">Administration</DialogTitle>
        <DialogDescription className="sr-only">
          Modelle, Einlesen, Retrieval, Tools, Benutzer und Verbindungen verwalten
        </DialogDescription>
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-border-base bg-surface p-2 md:w-56 md:flex-col md:border-r md:border-b-0 md:p-3">
            <p className="hidden px-3 pb-1 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground md:block">
              Administration
            </p>
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => onTabChange(t.id)}
                className={cn(
                  "flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                  tab === t.id
                    ? "bg-surface-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-hover hover:text-foreground",
                )}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </nav>
          <AdminNav.Provider value={onTabChange}>
            <div className="min-h-0 min-w-0 flex-1">
              {TABS.filter((t) => visited.includes(t.id) || t.id === tab).map((t) => (
                <div key={t.id} className={cn("h-full", t.id !== tab && "hidden")}>
                  {t.page}
                </div>
              ))}
            </div>
          </AdminNav.Provider>
        </div>
      </DialogContent>
    </Dialog>
  );
}
