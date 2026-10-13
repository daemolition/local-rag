import { useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  FolderOpen,
  Library,
  LogOut,
  Menu,
  NotebookText,
  Sparkles,
  SquarePen,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AccountDialog } from "@/components/AccountDialog";
import { AdminDialog, type AdminTab } from "@/components/AdminDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useIngestion } from "@/context/IngestionContext";
import { useSessions } from "@/context/SessionsContext";
import { useVersion } from "@/lib/useVersion";
import type { ChatSession } from "@/lib/types";

function IngestionBadge() {
  const { isIngesting } = useIngestion();
  if (!isIngesting) return null;
  return (
    <div className="flex items-center gap-1.5 rounded-lg bg-amber-500/80 px-3 py-1.5 text-xs font-medium text-white">
      <span className="size-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
      Dokumentenverarbeitung läuft
    </div>
  );
}

const itemClass = (active: boolean) =>
  cn(
    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
    active
      ? "bg-surface-muted font-medium text-foreground"
      : "text-foreground hover:bg-hover",
  );

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { logout, user, hasRole } = useAuth();
  const { sessions, remove } = useSessions();
  const navigate = useNavigate();
  const location = useLocation();
  const [deleteTarget, setDeleteTarget] = useState<ChatSession | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [adminTab, setAdminTab] = useState<AdminTab>("models");
  const version = useVersion();

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await remove(deleteTarget.id);
      if (location.pathname === `/c/${deleteTarget.id}`) navigate("/");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleteTarget(null);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-4 py-3.5">
        <Sparkles className="size-5 shrink-0" />
        <span className="text-sm font-semibold">Open Knowledge UI</span>
      </div>

      <div className="space-y-0.5 px-2">
        <NavLink
          to="/"
          end
          onClick={onNavigate}
          className={({ isActive }) => itemClass(isActive)}
        >
          <SquarePen className="size-4" />
          Neuer Chat
        </NavLink>
        <NavLink
          to="/uploads"
          onClick={onNavigate}
          className={({ isActive }) => itemClass(isActive)}
        >
          <FolderOpen className="size-4" />
          Meine Uploads
        </NavLink>
        <NavLink
          to="/knowledge"
          onClick={onNavigate}
          className={({ isActive }) => itemClass(isActive)}
        >
          <NotebookText className="size-4" />
          Knowledge
        </NavLink>
      </div>

      <p className="px-5 pb-1 pt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Chats
      </p>
      <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
        {sessions.length === 0 ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">
            Noch keine Chats
          </p>
        ) : (
          sessions.map((s) => (
            <NavLink
              key={s.id}
              to={`/c/${s.id}`}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(itemClass(isActive), "group justify-between")
              }
            >
              <span className="truncate">{s.title || "Neuer Chat"}</span>
              <button
                type="button"
                className="shrink-0 opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setDeleteTarget(s);
                }}
                aria-label="Chat löschen"
              >
                <Trash2 className="size-3.5" />
              </button>
            </NavLink>
          ))
        )}
      </nav>

      <div className="space-y-0.5 border-t border-border-base p-2">
        {hasRole("admin") ? (
          <button
            type="button"
            onClick={() => setAdminOpen(true)}
            className={cn(itemClass(false), "w-full text-left")}
          >
            <ShieldCheck className="size-4" />
            Administration
          </button>
        ) : null}
        <NavLink
          to="/summaries"
          onClick={onNavigate}
          className={({ isActive }) => itemClass(isActive)}
        >
          <Library className="size-4" />
          Meine Ablagen
        </NavLink>
        {user ? (
          <button
            type="button"
            onClick={() => setAccountOpen(true)}
            className="w-full truncate rounded-lg px-3 pt-2 text-left text-xs text-muted-foreground hover:text-foreground"
            title="Mein Konto / Passwort ändern"
          >
            {user.display_name} · {user.role}
            {version ? ` · v${version}` : ""}
          </button>
        ) : null}
        <div className="flex items-center gap-1 pt-1">
          <ThemeToggle />
          <Button variant="ghost" size="icon" title="Abmelden" onClick={logout}>
            <LogOut className="size-5" />
          </Button>
          <div className="ml-auto">
            <IngestionBadge />
          </div>
        </div>
      </div>

      <AccountDialog open={accountOpen} onOpenChange={setAccountOpen} />
      {hasRole("admin") ? (
        <AdminDialog
          open={adminOpen}
          onOpenChange={setAdminOpen}
          tab={adminTab}
          onTabChange={setAdminTab}
        />
      ) : null}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Chat löschen?"
        description={deleteTarget?.title ?? undefined}
        confirmLabel="Löschen"
        destructive
        onConfirm={confirmDelete}
      />
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      <div className="flex h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-border-base bg-surface lg:block">
          <SidebarContent />
        </aside>

        {mobileOpen ? (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileOpen(false)}
            />
            <aside className="absolute inset-y-0 left-0 w-64 bg-surface shadow-material-3">
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </aside>
          </div>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-3 border-b border-border-base bg-surface px-4 py-3 lg:hidden">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMobileOpen(true)}
              aria-label="Menü öffnen"
            >
              <Menu className="size-5" />
            </Button>
            <span className="font-semibold">Open Knowledge UI</span>
            <div className="ml-auto flex items-center gap-2">
              <IngestionBadge />
            </div>
          </header>
          <main className="min-h-0 flex-1 overflow-hidden">{children}</main>
        </div>
      </div>
    </>
  );
}

export { IngestionBadge };
