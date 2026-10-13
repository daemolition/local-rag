import { useEffect, useState } from "react";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, errorMessage } from "@/lib/api";
import type { Knowledge, SqlSource } from "@/lib/types";

interface Facts {
  version: string;
  tables: { name: string; columns: string[] }[];
  write_privilege: boolean | null;
}

type Dialect = SqlSource["dialect"];

const DEFAULT_PORTS: Record<Dialect, number> = { postgresql: 5432, mysql: 3306, mssql: 1433, sqlite: 0 };
const LABELS: Record<Dialect, string> = {
  postgresql: "PostgreSQL",
  mysql: "MySQL / MariaDB",
  mssql: "Microsoft SQL Server",
  sqlite: "SQLite (Datei im freigegebenen Ordner)",
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing?: Knowledge | null;
  onSaved: () => void;
}

// Anbinden und Bearbeiten einer SQL-Datenbank als Knowledge (nur lesend, live abgefragt).
export function SqlSourceDialog({ open, onOpenChange, existing, onSaved }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [dialect, setDialect] = useState<Dialect>("postgresql");
  const [host, setHost] = useState("");
  const [instance, setInstance] = useState("");
  const [port, setPort] = useState("5432");
  const [database, setDatabase] = useState("");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [hasPassword, setHasPassword] = useState(false);
  const [schema, setSchema] = useState("");
  const [facts, setFacts] = useState<Facts | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [blocked, setBlocked] = useState<Record<string, Set<string>>>({});
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const src = existing?.source_config as SqlSource | undefined;
    setName(existing?.name ?? "");
    setDescription(existing?.description ?? "");
    setDialect(src?.dialect ?? "postgresql");
    setHost(src?.host ?? "");
    setInstance(src?.instance ?? "");
    setPort(String(src?.port ?? 5432));
    setDatabase(src?.database ?? "");
    setUser(src?.user ?? "");
    setPassword("");
    setHasPassword(!!src?.has_password);
    setSchema(src?.schema ?? "");
    setFacts(null);
    setSelected(new Set(src?.tables ?? []));
    setBlocked(Object.fromEntries(Object.entries(src?.blocked_columns ?? {}).map(([t, c]) => [t, new Set(c)])));
  }, [open, existing]);

  const source = () => {
    // leer = alle Tabellen; nur senden, wenn eine Auswahl getroffen wurde
    const all = facts ? facts.tables.length : 0;
    const tables = facts ? (selected.size && selected.size < all ? [...selected] : []) : [...selected];
    return {
      dialect,
      host: host.trim(),
      instance: dialect === "mssql" ? instance.trim() : "",
      port: Number(port) || DEFAULT_PORTS[dialect],
      database: database.trim(),
      user: user.trim(),
      password,
      schema: schema.trim(),
      tables,
      blocked_columns: Object.fromEntries(
        Object.entries(blocked)
          .filter(([, c]) => c.size)
          .map(([t, c]) => [t, [...c]]),
      ),
    };
  };

  const test = async () => {
    setTesting(true);
    setFacts(null);
    try {
      const f = await api.post<Facts>("/api/knowledge/sql/test", { knowledge_id: existing?.id, source: source() });
      setFacts(f);
      // Standard: alle Tabellen freigegeben
      setSelected((prev) =>
        prev.size ? new Set([...prev].filter((t) => f.tables.some((x) => x.name === t))) : new Set(f.tables.map((t) => t.name)),
      );
    } catch (e) {
      toast.error(errorMessage(e), { duration: 12000 });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const body = { name: name.trim(), description: description.trim(), source: source() };
      if (existing) await api.patch(`/api/knowledge/${existing.id}`, body);
      else await api.post("/api/knowledge", { ...body, kind: "sql" });
      toast.success(existing ? "Quelle gespeichert" : "SQL-Datenbank angebunden");
      onSaved();
      onOpenChange(false);
    } catch (e) {
      toast.error(errorMessage(e), { duration: 12000 });
    } finally {
      setBusy(false);
    }
  };

  const toggle = (table: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(table)) n.delete(table);
      else n.add(table);
      return n;
    });
  const toggleColumn = (table: string, column: string) =>
    setBlocked((b) => {
      const n = new Set(b[table] ?? []);
      if (n.has(column)) n.delete(column);
      else n.add(column);
      return { ...b, [table]: n };
    });

  const file = dialect === "sqlite";
  const valid = name.trim() && database.trim() && (file || (host.trim() && user.trim()));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{existing ? "SQL-Datenbank bearbeiten" : "SQL-Datenbank anbinden"}</DialogTitle>
          <DialogDescription>
            Das Modell fragt die Datenbank bei jeder Frage live und nur lesend ab; die Daten werden nicht kopiert. Lege dafür
            einen Datenbank-Benutzer an, der nur SELECT darf.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label className="text-xs">Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Beschreibung</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Datenbanktyp</Label>
            <Select
              value={dialect}
              onValueChange={(v) => {
                setDialect(v as Dialect);
                setPort(String(DEFAULT_PORTS[v as Dialect] || ""));
                setFacts(null);
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(LABELS) as Dialect[]).map((d) => (
                  <SelectItem key={d} value={d}>
                    {LABELS[d]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs">{file ? "Dateiname (z. B. shop.db)" : "Datenbank"}</Label>
            <Input value={database} onChange={(e) => setDatabase(e.target.value)} />
          </div>
          {file ? null : (
            <>
              <div className="space-y-1">
                <Label className="text-xs">Host</Label>
                <Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="db.intern oder host.docker.internal" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Port</Label>
                <Input inputMode="numeric" value={port} onChange={(e) => setPort(e.target.value.replace(/\D/g, ""))} />
              </div>
              {dialect === "mssql" ? (
                <div className="space-y-1">
                  <Label className="text-xs">Instanz (optional)</Label>
                  <Input value={instance} onChange={(e) => setInstance(e.target.value)} placeholder="z. B. SQLEXPRESS" />
                  <p className="text-xs text-muted-foreground">Bei benannter Instanz findet der SQL Browser (UDP 1434) den Port.</p>
                </div>
              ) : null}
              <div className="space-y-1">
                <Label className="text-xs">Benutzer</Label>
                <Input value={user} onChange={(e) => setUser(e.target.value)} autoComplete="off" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Passwort</Label>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  placeholder={hasPassword ? "unverändert" : ""}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Schema (optional)</Label>
                <Input value={schema} onChange={(e) => setSchema(e.target.value)} />
              </div>
            </>
          )}
        </div>

        <div className="space-y-2">
          <Button variant="secondary" size="sm" onClick={test} disabled={testing || !valid}>
            {testing ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            Verbindung testen
          </Button>
          {facts ? (
            <div className="space-y-2 rounded-lg border border-border-base p-3 text-sm">
              <p className="text-muted-foreground">{facts.version}</p>
              {facts.write_privilege === true ? (
                <p className="rounded bg-amber-500/15 px-2 py-1 text-amber-700">
                  Dieser Benutzer darf schreiben. Lege besser einen Benutzer nur mit SELECT-Recht an; die App führt trotzdem
                  nur lesende Abfragen aus.
                </p>
              ) : null}
              <p className="font-medium">
                Freigegebene Tabellen ({selected.size} von {facts.tables.length})
              </p>
              <div className="max-h-64 space-y-1 overflow-y-auto">
                {facts.tables.map((t) => (
                  <details key={t.name} className="rounded border border-border-base px-2 py-1">
                    <summary className="flex cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selected.has(t.name)}
                        onChange={() => toggle(t.name)}
                        onClick={(e) => e.stopPropagation()}
                      />
                      <span>{t.name}</span>
                      <span className="text-xs text-muted-foreground">{t.columns.length} Spalten</span>
                    </summary>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 pl-6 text-xs">
                      {t.columns.map((c) => (
                        <label key={c} className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={blocked[t.name]?.has(c) ?? false}
                            onChange={() => toggleColumn(t.name, c)}
                          />
                          {c} <span className="text-muted-foreground">sperren</span>
                        </label>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Abbrechen
          </Button>
          <Button onClick={save} disabled={busy || !valid}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : null}
            Speichern
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
