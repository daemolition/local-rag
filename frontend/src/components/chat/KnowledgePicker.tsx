import { ChevronDown, NotebookText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Knowledge } from "@/lib/types";

interface KnowledgePickerProps {
  knowledge: Knowledge[];
  // null = alle Bereiche durchsuchen
  selectedIds: number[] | null;
  onChange: (ids: number[] | null) => void;
}

export function KnowledgePicker({
  knowledge,
  selectedIds,
  onChange,
}: KnowledgePickerProps) {
  const effective =
    selectedIds === null
      ? knowledge.map((k) => k.id)
      : selectedIds.filter((id) => knowledge.some((k) => k.id === id));

  const label =
    effective.length === knowledge.length
      ? "Alle Knowledge"
      : effective.length === 0
        ? "Kein Knowledge"
        : effective.length === 1
          ? (knowledge.find((k) => k.id === effective[0])?.name ?? "Knowledge")
          : `${effective.length} Knowledge`;

  const toggle = (id: number, checked: boolean) => {
    const next = checked
      ? [...new Set([...effective, id])]
      : effective.filter((x) => x !== id);
    onChange(next.length === knowledge.length ? null : next);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 gap-1.5 rounded-full px-3 text-muted-foreground"
          title="Durchsuchtes Knowledge wählen"
        >
          <NotebookText className="size-4" />
          <span className="max-w-40 truncate">{label}</span>
          <ChevronDown className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Wissen für diese Antwort</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {knowledge.map((k) => (
          <DropdownMenuCheckboxItem
            key={k.id}
            checked={effective.includes(k.id)}
            onCheckedChange={(c) => toggle(k.id, Boolean(c))}
            onSelect={(e) => e.preventDefault()}
          >
            <span className="truncate">{k.name}</span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
