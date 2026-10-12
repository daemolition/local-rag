import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, errorMessage } from "@/lib/api";

interface Preview {
  filename: string;
  columns: string[];
  rows: string[][];
  total_rows: number;
  truncated: boolean;
}

// Vorschau einer CSV/Excel-Datei (erste Zeilen) mit Download der vollständigen Datei.
export function DataFileDialog({
  filename,
  knowledgeQuery,
  onOpenChange,
}: {
  filename: string | null;
  knowledgeQuery: string;
  onOpenChange: (open: boolean) => void;
}) {
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = filename ? `/api/data-files/${encodeURIComponent(filename)}` : "";

  useEffect(() => {
    if (!filename) return;
    setData(null);
    setError(null);
    let active = true;
    api
      .get<Preview>(`${base}?${knowledgeQuery}`)
      .then((r) => active && setData(r))
      .catch((e) => active && setError(errorMessage(e)));
    return () => {
      active = false;
    };
  }, [filename, base, knowledgeQuery]);

  return (
    <Dialog open={filename !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>{filename}</DialogTitle>
          <DialogDescription>
            {data
              ? `${data.total_rows} Zeilen, ${data.columns.length} Spalten${
                  data.truncated ? ` – angezeigt werden die ersten ${data.rows.length}` : ""
                }`
              : "Vorschau"}
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border-base">
          {error ? (
            <p className="p-3 text-sm text-muted-foreground">{error}</p>
          ) : data === null ? (
            <p className="flex items-center gap-2 p-3 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Lade…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {data.columns.map((c, i) => (
                    <TableHead key={i} className="whitespace-nowrap">
                      {c}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.rows.map((row, i) => (
                  <TableRow key={i}>
                    {row.map((cell, j) => (
                      <TableCell key={j} className="whitespace-nowrap text-xs">
                        {cell}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {filename ? (
          <div className="flex justify-end">
            <Button variant="secondary" size="sm" asChild>
              <a href={`${base}?download=1&${knowledgeQuery}`}>
                <Download className="size-4" />
                Herunterladen
              </a>
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
