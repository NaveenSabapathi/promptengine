import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { User, OAuthProvider } from "@promptengine/shared-types";
import { api, APIException } from "@/lib/api";
interface Session {
  user: User | null;
  linked: OAuthProvider[];
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  clear: () => void;
}
const Context = createContext<Session | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [linked, setLinked] = useState<OAuthProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  async function refresh() {
    setError("");
    try {
      const result = await api<{
        user: User;
        linked_providers: OAuthProvider[];
      }>("/api/auth/me");
      setUser(result.user);
      setLinked(result.linked_providers);
    } catch (e) {
      setUser(null);
      if (!(e instanceof APIException && e.status === 401))
        setError(e instanceof Error ? e.message : "Cannot load your session");
    } finally {
      setLoading(false);
    }
  }
  function clear() {
    sessionStorage.removeItem("active-team");
    setUser(null);
    setLinked([]);
  }
  useEffect(() => {
    void refresh();
    window.addEventListener("session-expired", clear);
    return () => window.removeEventListener("session-expired", clear);
  }, []);
  return (
    <Context.Provider value={{ user, linked, loading, error, refresh, clear }}>
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("Session context missing");
  return value;
}
