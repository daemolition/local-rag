import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import type { AuthUser, Role } from "@/lib/types";

const ROLE_ORDER: Role[] = ["user", "editor", "admin"];

interface AuthContextValue {
  authenticated: boolean;
  loading: boolean;
  user: AuthUser | null;
  // true, wenn die Rolle des Nutzers mindestens `role` ist (admin ⊃ editor ⊃ user).
  hasRole: (role: Role) => boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api
      .get<{ user: AuthUser }>("/api/auth/me")
      .then((res) => active && setUser(res.user))
      .catch(() => active && setUser(null))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post<{ user: AuthUser }>("/api/auth/login", {
      username,
      password,
    });
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout");
    setUser(null);
  }, []);

  const hasRole = useCallback(
    (role: Role) =>
      user !== null && ROLE_ORDER.indexOf(user.role) >= ROLE_ORDER.indexOf(role),
    [user],
  );

  return (
    <AuthContext.Provider
      value={{ authenticated: user !== null, loading, user, hasRole, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth muss innerhalb von AuthProvider laufen");
  return ctx;
}
