import { useEffect, useMemo, useState } from "react";
import { Plus, Users, User, X } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api";
import type { AccessInfo, AccessLevel, Grant, Principals } from "@/lib/types";

interface AccessDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  publicLabel: string;
  readLabel: string;
  // Modelle kennen nur "nutzen"; Knowledge zusätzlich "verwalten".
  allowWrite: boolean;
  load: () => Promise<AccessInfo>;
  save: (info: AccessInfo) => Promise<AccessInfo>;
}

const key = (g: Pick<Grant, "principal_type" | "principal_id">) =>
  `${g.principal_type}:${g.principal_id}`;

export function AccessDialog({
  open,
  onOpenChange,
  title,
  description,
  publicLabel,
  readLabel,
  allowWrite,
  load,
  save,
}: AccessDialogProps) {
  const [info, setInfo] = useState<AccessInfo | null>(null);
  const [principals, setPrincipals] = useState<Principals>({ users: [], groups: [] });
  const [pick, setPick] = useState("");
  const [pickLevel, setPickLevel] = useState<AccessLevel>("read");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setInfo(null);
    setPick("");
    Promise.all([load(), api.get<Principals>("/api/principals")])
      .then(([a, p]) => {
        setInfo(a);
        setPrincipals(p);
      })
      .catch((e) => {
        toast.error(errorMessage(e));
        onOpenChange(false);
      });
    // load/onOpenChange ändern sich bei jedem Render des Aufrufers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const available = useMemo(() => {
    const taken = new Set((info?.grants ?? []).map(key));
    return {
      users: principals.users.filter((u) => !taken.has(`user:${u.id}`)),
      groups: principals.groups.filter((g) => !taken.has(`group:${g.id}`)),
    };
  }, [info, principals]);

  const nameOf = (g: Grant) =>
    g.name ??
    (g.principal_type === "user"
      ? principals.users.find((u) => u.id === g.principal_id)?.name
      : principals.groups.find((x) => x.id === g.principal_id)?.name) ??
    "?";

  const add = () => {
    if (!pick || !info) return;
    const [type, id] = pick.split(":");
    const name =
      type === "user"
        ? principals.users.find((u) => u.id === Number(id))?.name
        : principals.groups.find((g) => g.id === Number(id))?.name;
    setInfo({
      ...info,
      grants: [
        ...info.grants,
        {
          principal_type: type as Grant["principal_type"],
          principal_id: Number(id),
          name,
          access: allowWrite ? pickLevel : "read",
        },
      ],
    });
    setPick("");
  };

  const submit = async () => {
    if (!info) return;
    setBusy(true);
    try {
      await save(info);
      toast.success("Freigaben gespeichert");
      onOpenChange(false);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>

        {info === null ? (
          <p className="text-muted-foreground">Lade…</p>
        ) : (
          <div className="space-y-5">
            <div className="flex items-start justify-between gap-4 rounded-lg border border-border-base px-3 py-2">
              <div>
                <Label htmlFor="acc-public" className="cursor-pointer">
                  {publicLabel}
                </Label>
                <p className="text-xs text-muted-foreground">
                  Ohne diesen Schalter gilt nur die Liste unten (und Admins).
                </p>
              </div>
              <Switch
                id="acc-public"
                checked={info.is_public}
                onCheckedChange={(v) => setInfo({ ...info, is_public: v })}
              />
            </div>

            <section className="space-y-2">
              <h3 className="text-sm font-semibold">Freigegeben für</h3>
              {info.grants.length === 0 ? (
                <p className="text-sm text-muted-foreground">Niemand ausgewählt.</p>
              ) : (
                <div className="divide-y divide-border-base rounded-lg border border-border-base">
                  {info.grants.map((g) => (
                    <div key={key(g)} className="flex items-center gap-3 px-3 py-2">
                      {g.principal_type === "group" ? (
                        <Users className="size-4 shrink-0 text-muted-foreground" />
                      ) : (
                        <User className="size-4 shrink-0 text-muted-foreground" />
                      )}
                      <span className="min-w-0 flex-1 truncate text-sm">{nameOf(g)}</span>
                      {allowWrite ? (
                        <Select
                          value={g.access}
                          onValueChange={(v) =>
                            setInfo({
                              ...info,
                              grants: info.grants.map((x) =>
                                key(x) === key(g) ? { ...x, access: v as AccessLevel } : x,
                              ),
                            })
                          }
                        >
                          <SelectTrigger className="w-36">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="read">{readLabel}</SelectItem>
                            <SelectItem value="write">Verwalten</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : null}
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        title="Entfernen"
                        onClick={() =>
                          setInfo({
                            ...info,
                            grants: info.grants.filter((x) => key(x) !== key(g)),
                          })
                        }
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-1">
                <Select value={pick} onValueChange={setPick}>
                  <SelectTrigger className="min-w-52 flex-1">
                    <SelectValue placeholder="Nutzer oder Gruppe hinzufügen…" />
                  </SelectTrigger>
                  <SelectContent>
                    {available.groups.length > 0 ? (
                      <SelectGroup>
                        <SelectLabel>Gruppen</SelectLabel>
                        {available.groups.map((g) => (
                          <SelectItem key={g.id} value={`group:${g.id}`}>
                            {g.name}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ) : null}
                    {available.users.length > 0 ? (
                      <SelectGroup>
                        <SelectLabel>Nutzer</SelectLabel>
                        {available.users.map((u) => (
                          <SelectItem key={u.id} value={`user:${u.id}`}>
                            {u.name} ({u.username})
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    ) : null}
                  </SelectContent>
                </Select>
                {allowWrite ? (
                  <Select
                    value={pickLevel}
                    onValueChange={(v) => setPickLevel(v as AccessLevel)}
                  >
                    <SelectTrigger className="w-36">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="read">{readLabel}</SelectItem>
                      <SelectItem value="write">Verwalten</SelectItem>
                    </SelectContent>
                  </Select>
                ) : null}
                <Button variant="secondary" onClick={add} disabled={!pick}>
                  <Plus className="size-4" />
                  Hinzufügen
                </Button>
              </div>
            </section>
          </div>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={submit} disabled={info === null || busy}>
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
