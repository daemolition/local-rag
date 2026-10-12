import { Check, ChevronDown, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ModelEntry } from "@/lib/types";

interface ModelPickerProps {
  models: ModelEntry[];
  selected: string;
  onChange: (ref: string) => void;
}

export function ModelPicker({ models, selected, onChange }: ModelPickerProps) {
  const current = models.find((m) => m.ref === selected);

  const groups = new Map<string, ModelEntry[]>();
  for (const m of models) {
    groups.set(m.connection_name, [...(groups.get(m.connection_name) ?? []), m]);
  }
  const multiple = groups.size > 1;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 gap-1.5 rounded-full px-3 text-muted-foreground"
          title="Modell wählen"
        >
          <Cpu className="size-4" />
          <span className="max-w-48 truncate">{current?.name ?? "Modell wählen"}</span>
          <ChevronDown className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-96 w-72 overflow-y-auto">
        {[...groups.entries()].map(([connection, items], i) => (
          <div key={connection}>
            {i > 0 ? <DropdownMenuSeparator /> : null}
            {multiple ? <DropdownMenuLabel>{connection}</DropdownMenuLabel> : null}
            {items.map((m) => (
              <DropdownMenuItem
                key={m.ref}
                onSelect={() => onChange(m.ref)}
                className="justify-between gap-2"
              >
                <span className="truncate">{m.name}</span>
                {m.ref === selected ? <Check className="size-4 shrink-0" /> : null}
              </DropdownMenuItem>
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
