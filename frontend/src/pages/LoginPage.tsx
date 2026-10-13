import { useEffect, useState, type FormEvent } from "react";
import { FileText, KeyRound, Lock, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [oidc, setOidc] = useState<{ enabled: boolean; name: string } | null>(null);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("login_error")) {
      setError("Die Anmeldung über den Anbieter ist fehlgeschlagen.");
      window.history.replaceState(null, "", window.location.pathname);
    }
    api
      .get<{ oidc: { enabled: boolean; name: string } }>("/api/auth/providers")
      .then((p) => setOidc(p.oidc))
      .catch(() => setOidc(null));
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md rounded-2xl bg-surface p-8 shadow-material-3">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary">
            <FileText className="size-8 text-primary-text" />
          </div>
          <h1 className="text-2xl font-bold">Open Knowledge UI</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Intelligente Dokumentenanalyse
          </p>
        </div>

        {error ? (
          <div className="mb-6 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </div>
        ) : null}

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">Benutzername</Label>
            <div className="relative">
              <User className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="username"
                className="pl-9"
                placeholder="Benutzername"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                required
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Passwort</Label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="password"
                type="password"
                className="pl-9"
                placeholder="Passwort eingeben"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Anmelden…" : "Anmelden"}
          </Button>
        </form>

        {oidc?.enabled ? (
          <Button variant="outline" className="mt-3 w-full" asChild>
            <a href="/api/auth/oidc/login">
              <KeyRound className="size-4" />
              Mit {oidc.name} anmelden
            </a>
          </Button>
        ) : null}

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Lokale KI-gestützte Dokumentenanalyse
        </p>
      </div>
    </div>
  );
}
