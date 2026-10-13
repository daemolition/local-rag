import { type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AppShell } from "@/components/Layout";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuth } from "@/context/AuthContext";
import type { Role } from "@/lib/types";
import { SessionsProvider } from "@/context/SessionsContext";
import { ChatPage } from "@/pages/ChatPage";
import { EditSummaryPage } from "@/pages/EditSummaryPage";
import { MyUploadsPage } from "@/pages/MyUploadsPage";
import { LoginPage } from "@/pages/LoginPage";
import { SummariesPage } from "@/pages/SummariesPage";
import { KnowledgeDetailPage } from "@/pages/KnowledgeDetailPage";
import { KnowledgePage } from "@/pages/KnowledgePage";
import { VectorDbDetailPage } from "@/pages/VectorDbDetailPage";
import { VectorDbPage } from "@/pages/VectorDbPage";

// Blendet eine Seite für zu niedrige Rollen aus (die API prüft zusätzlich).
function Guard({ role, children }: { role: Role; children: ReactNode }) {
  const { hasRole } = useAuth();
  return hasRole(role) ? <>{children}</> : <Navigate to="/" replace />;
}

export function App() {
  const { authenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 size-5 animate-spin" />
        Lade…
      </div>
    );
  }

  if (!authenticated) {
    return (
      <>
        <LoginPage />
        <Toaster />
      </>
    );
  }

  return (
    <TooltipProvider>
      <SessionsProvider>
      <AppShell>
        <div className="h-full overflow-y-auto">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/c/:sessionId" element={<ChatPage />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            <Route path="/admin/*" element={<Navigate to="/" replace />} />
            <Route path="/uploads" element={<MyUploadsPage />} />
            <Route path="/knowledge" element={<Guard role="user"><KnowledgePage /></Guard>} />
            <Route path="/knowledge/:id" element={<Guard role="user"><KnowledgeDetailPage /></Guard>} />
            <Route path="/documents" element={<Navigate to="/knowledge" replace />} />
            <Route
              path="/documents/upload"
              element={<Navigate to="/knowledge" replace />}
            />
            <Route path="/vectordb" element={<Guard role="user"><VectorDbPage /></Guard>} />
            <Route path="/vectordb/:docId" element={<Guard role="user"><VectorDbDetailPage /></Guard>} />
            <Route path="/summaries" element={<SummariesPage />} />
            <Route path="/summaries/:filename" element={<EditSummaryPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </AppShell>
      </SessionsProvider>
      <Toaster />
    </TooltipProvider>
  );
}
