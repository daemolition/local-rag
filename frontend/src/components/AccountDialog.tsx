import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { api, errorMessage } from "@/lib/api";
import { useVersion } from "@/lib/useVersion";

// Eigenes Konto: Passwort ändern (für jede Rolle erreichbar).
export function AccountDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { user } = useAuth();
  const version = useVersion();
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setOldPw("");
      setNewPw("");
      setRepeat("");
    }
  }, [open]);

  const mismatch = repeat !== "" && newPw !== repeat;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (mismatch || !newPw) return;
    setBusy(true);
    try {
      await api.post("/api/auth/change-password", {
        old_password: oldPw,
        new_password: newPw,
      });
      toast.success("Passwort geändert");
      onOpenChange(false);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Mein Konto</DialogTitle>
            <DialogDescription>
              {user?.display_name} · {user?.username} · {user?.role}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="acc-old">Aktuelles Passwort</Label>
            <Input
              id="acc-old"
              type="password"
              autoComplete="current-password"
              value={oldPw}
              onChange={(e) => setOldPw(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="acc-new">Neues Passwort</Label>
            <Input
              id="acc-new"
              type="password"
              autoComplete="new-password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="acc-repeat">Neues Passwort wiederholen</Label>
            <Input
              id="acc-repeat"
              type="password"
              autoComplete="new-password"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              required
            />
            {mismatch ? (
              <p className="text-xs text-destructive">Passwörter stimmen nicht überein.</p>
            ) : null}
          </div>
          {version ? (
            <p className="text-xs text-muted-foreground">Version v{version}</p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={busy || mismatch || !newPw || !oldPw}>
              Passwort ändern
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
