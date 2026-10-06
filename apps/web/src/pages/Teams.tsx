import { useEffect, useState } from "react";
import { api, post, errorText } from "@/lib/api";
import { Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
type Team = { id: string; name: string; role: string };
export default function Teams() {
  const [members, setMembers] = useState<
    { id: string; email: string; role: string }[]
  >([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("MEMBER");
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(
    new URLSearchParams(location.hash.slice(1)).get("invite") || "",
  );
  const active = sessionStorage.getItem("active-team") || "";
  const loadMembers = () =>
    active
      ? api<{ members: { id: string; email: string; role: string }[] }>(
          `/api/teams/${active}/members`,
        ).then((r) => setMembers(r.members))
      : Promise.resolve();
  const refresh = () =>
    api<{ teams: Team[] }>("/api/teams").then((r) => setTeams(r.teams));
  useEffect(() => {
    refresh()
      .then(loadMembers)
      .catch((e) => setError(errorText(e)));
    if (location.hash)
      history.replaceState(history.state, "", location.pathname);
  }, []);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
      await loadMembers();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>Team workspaces</h1>
      <Notice error={error} />
      <p>
        History and custom presets use the workspace selected below. Membership
        is verified by the server on every request.
      </p>
      <section className="card">
        <label htmlFor="active-team">Active workspace</label>
        <select
          id="active-team"
          value={active}
          onChange={(e) => {
            if (e.target.value)
              sessionStorage.setItem("active-team", e.target.value);
            else sessionStorage.removeItem("active-team");
            location.reload();
          }}
        >
          <option value="">Personal workspace</option>
          {teams.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} · {t.role}
            </option>
          ))}
        </select>
      </section>
      {active && (
        <section className="card">
          <h2>Workspace members</h2>
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id}>
                  <td>{m.email}</td>
                  <td>{m.role}</td>
                  <td>
                    {m.role !== "OWNER" &&
                      ["OWNER", "ADMIN"].includes(
                        teams.find((t) => t.id === active)?.role || "",
                      ) && (
                        <Button
                          variant="outline"
                          disabled={busy}
                          onClick={() =>
                            void run(async () => {
                              await api(
                                `/api/teams/${active}/members/${m.id}`,
                                { method: "DELETE" },
                              );
                            })
                          }
                        >
                          Remove access
                        </Button>
                      )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <section className="card">
        <h2>Create workspace</h2>
        <label htmlFor="team-name">Workspace name</label>
        <Input
          id="team-name"
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
        />
        <Button
          disabled={busy || !name}
          onClick={() =>
            void run(async () => {
              await post("/api/teams", { name });
              setName("");
            })
          }
        >
          Create workspace
        </Button>
      </section>
      <section className="card">
        <h2>Invite a colleague</h2>
        <label htmlFor="invite-email">Email address</label>
        <Input
          id="invite-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <label htmlFor="invite-role">Role</label>
        <select
          id="invite-role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option>MEMBER</option>
          <option>ADMIN</option>
        </select>
        <Button
          disabled={
            busy ||
            !active ||
            !email ||
            !["OWNER", "ADMIN"].includes(
              teams.find((t) => t.id === active)?.role || "",
            )
          }
          onClick={() =>
            void run(async () => {
              const r = await post<{ invitation_url: string }>(
                `/api/teams/${active}/invitations`,
                { email, role },
              );
              setUrl(r.invitation_url);
            })
          }
        >
          Create invitation
        </Button>
        {url && (
          <p>
            Share this private invitation with the named recipient:{" "}
            <a href={url}>{url}</a>
          </p>
        )}
      </section>
      <section className="card">
        <h2>Accept invitation</h2>
        <label htmlFor="invite-token">Invitation token</label>
        <Input
          id="invite-token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <Button
          disabled={busy || !token}
          onClick={() =>
            void run(async () => {
              await post("/api/teams/accept", { token });
              setToken("");
            })
          }
        >
          Join workspace
        </Button>
      </section>
    </>
  );
}
