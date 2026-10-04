import {
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  LayoutDashboard,
  Library,
  Settings,
  Puzzle,
  LogOut,
  ArrowUpRight,
} from "lucide-react";
import { useState } from "react";
import { useAuth } from "./auth";
import { api, errorText } from "./lib/api";
import { Brand, Busy, Notice } from "./components/common";
import { Button } from "./components/ui/button";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Workspace from "./pages/Workspace";
import History from "./pages/History";
import SettingsPage from "./pages/Settings";
import Extensions from "./pages/Extensions";
import Presets from "./pages/Presets";
function Shell() {
  const auth = useAuth();
  const location = useLocation();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (auth.loading) return <Busy />;
  if (auth.error)
    return (
      <div className="error-boundary">
        <Notice error={auth.error} />
        <Button onClick={() => void auth.refresh()}>Retry connection</Button>
      </div>
    );
  if (!auth.user)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  async function logout() {
    setBusy(true);
    try {
      await api("/api/auth/logout", { method: "POST" });
      auth.clear();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <div className="team-chip">
          <span className="avatar">{auth.user.email[0].toUpperCase()}</span>
          <div>
            <strong>Personal workspace</strong>
            <span>Ideas, with direction.</span>
          </div>
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Workspace navigation">
          {[
            ["/workspace", "Prompt editor", LayoutDashboard],
            ["/history", "Saved prompts", Library],
            ["/presets", "Custom presets", Puzzle],
            ["/settings", "Settings & billing", Settings],
          ].map(([path, label, Icon]) => {
            const C = Icon as typeof LayoutDashboard;
            return (
              <NavLink key={String(path)} end to={String(path)}>
                <C size={17} />
                {String(label)}
              </NavLink>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="extension-note">
            <Puzzle size={20} />
            <strong>Take clarity with you</strong>
            <p>Approve your browser extension here when it is ready.</p>
            <NavLink to="/settings/extensions">
              Connect a browser <ArrowUpRight size={14} />
            </NavLink>
          </div>
          <div className="account">
            <span className="avatar">{auth.user.email[0].toUpperCase()}</span>
            <span title={auth.user.email}>{auth.user.email}</span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              disabled={busy}
              onClick={() => void logout()}
            >
              <LogOut />
            </Button>
          </div>
        </div>
      </aside>
      <div className="main-area">
        <div className="topbar" role="banner">
          <span>
            <span className="status-dot" /> Your private prompt workspace
          </span>
          <span className="topbar-caption">Built for thoughtful work.</span>
          <Button
            className="hidden max-[650px]:inline-flex"
            variant="ghost"
            size="icon"
            aria-label="Sign out"
            disabled={busy}
            onClick={() => void logout()}
          >
            <LogOut />
          </Button>
        </div>
        <main className="page">
          <Notice error={error} />
          <Outlet />
        </main>
        <footer className="app-footer">
          PromptEngine <span>Clarity before execution.</span>
        </footer>
      </div>
    </div>
  );
}
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Login signup />} />
      <Route element={<Shell />}>
        <Route path="/workspace" element={<Workspace />} />
        <Route path="/history" element={<History />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/extensions" element={<Extensions />} />
        <Route path="/presets" element={<Presets />} />
      </Route>
      <Route
        path="*"
        element={
          <div className="error-boundary">
            <h1>Page not found</h1>
            <p>Return to your workspace to keep building.</p>
            <Button asChild>
              <NavLink to="/workspace">Open workspace</NavLink>
            </Button>
          </div>
        }
      />
    </Routes>
  );
}
