import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import type { ChatSession } from "@/lib/types";

interface SessionsContextValue {
  sessions: ChatSession[];
  reload: () => Promise<ChatSession[]>;
  remove: (id: string) => Promise<void>;
}

const SessionsContext = createContext<SessionsContextValue>({
  sessions: [],
  reload: async () => [],
  remove: async () => {},
});

// Chat-Verlauf für Sidebar und Chat-Seite (die Sidebar steht auf jeder Seite).
export function SessionsProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  const reload = useCallback(async () => {
    try {
      const data = await api.get<ChatSession[]>("/api/sessions");
      setSessions(data);
      return data;
    } catch (e) {
      console.error(e);
      return [];
    }
  }, []);

  const remove = useCallback(
    async (id: string) => {
      await api.del(`/api/sessions/${id}`);
      await reload();
    },
    [reload],
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <SessionsContext.Provider value={{ sessions, reload, remove }}>
      {children}
    </SessionsContext.Provider>
  );
}

export function useSessions(): SessionsContextValue {
  return useContext(SessionsContext);
}
