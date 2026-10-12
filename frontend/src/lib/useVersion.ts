import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let cached: Promise<string> | null = null;

// Version der Anwendung (einmal geladen, dann gecacht).
export function useVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    cached ??= api
      .get<{ version: string }>("/api/version")
      .then((r) => r.version)
      .catch(() => "");
    let active = true;
    void cached.then((v) => active && setVersion(v || null));
    return () => {
      active = false;
    };
  }, []);

  return version;
}
