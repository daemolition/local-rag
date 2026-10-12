import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";

interface IngestionContextValue {
  isIngesting: boolean;
}

const IngestionContext = createContext<IngestionContextValue>({
  isIngesting: false,
});

export function IngestionProvider({ children }: { children: ReactNode }) {
  const [isIngesting, setIsIngesting] = useState(false);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const data = await api.get<{ is_ingesting: boolean }>(
          "/api/ingestion-status",
        );
        if (active) setIsIngesting(Boolean(data.is_ingesting));
      } catch {
        if (active) setIsIngesting(false);
      }
    };
    check();
    const interval = setInterval(check, 5000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <IngestionContext.Provider value={{ isIngesting }}>
      {children}
    </IngestionContext.Provider>
  );
}

export function useIngestion(): IngestionContextValue {
  return useContext(IngestionContext);
}
