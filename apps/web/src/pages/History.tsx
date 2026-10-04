import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Search,
  Copy,
  Trash2,
  Pencil,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import type { PromptList, SavedPrompt } from "@promptengine/shared-types";
import { api, errorText } from "@/lib/api";
import { copyText, date } from "@/lib/utils";
import { Busy, Empty, Heading, Notice } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
export default function History() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<PromptList>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<SavedPrompt>();
  const [editing, setEditing] = useState(false);
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const [remove, setRemove] = useState<SavedPrompt>();
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    api<PromptList>(
      `/api/prompts?page=${page}&per_page=20&q=${encodeURIComponent(search)}`,
    )
      .then((r) => {
        if (alive) setData(r);
      })
      .catch((e) => {
        if (alive) setError(errorText(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [page, search, refresh]);
  async function copy(content: string) {
    try {
      await copyText(content);
      setMessage("Prompt copied.");
    } catch (e) {
      setError(errorText(e));
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const r = await api<{ prompt: SavedPrompt }>(
        `/api/prompts/${selected.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            title: selected.title,
            content: selected.content,
            tags: tags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean),
          }),
        },
      );
      setSelected(r.prompt);
      setEditing(false);
      setRefresh((x) => x + 1);
      setMessage("Prompt updated.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function deletePrompt() {
    if (!remove) return;
    setBusy(true);
    try {
      await api(`/api/prompts/${remove.id}`, { method: "DELETE" });
      if (selected?.id === remove.id) setSelected(undefined);
      setRemove(undefined);
      if (data?.prompts.length === 1 && page > 1) setPage(page - 1);
      else setRefresh((x) => x + 1);
      setMessage("Prompt deleted.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="heading-row">
        <Heading
          eyebrow="YOUR PROMPT LIBRARY"
          title="Good prompts are worth keeping."
          description="Find, revisit, and refine the prompts you chose to save."
        />
        <Button asChild>
          <Link to="/workspace">
            New prompt <ArrowUpRight />
          </Link>
        </Button>
      </div>
      <Notice error={error} message={message} />
      <section className="panel history-panel">
        <form
          className="search-bar"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(query);
            setPage(1);
          }}
        >
          <Search size={18} />
          <Input
            aria-label="Search saved prompt titles"
            placeholder="Search prompt titles…"
            value={query}
            maxLength={200}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Button type="submit" variant="outline">
            Search
          </Button>
        </form>
        {loading ? (
          <Busy text="Loading saved prompts…" />
        ) : data?.prompts.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Prompt</th>
                    <th>Tags</th>
                    <th>Saved</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.prompts.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <button
                          className="prompt-title"
                          onClick={() => {
                            setSelected(p);
                            setEditing(false);
                          }}
                        >
                          {p.title}
                        </button>
                        <p className="prompt-preview">
                          {p.content.slice(0, 100)}
                        </p>
                      </td>
                      <td>
                        <div className="tags">
                          {p.tags.map((t) => (
                            <span key={t}>{t}</span>
                          ))}
                        </div>
                      </td>
                      <td className="nowrap muted">{date(p.created_at)}</td>
                      <td>
                        <div className="row-actions">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Copy ${p.title}`}
                            onClick={() => void copy(p.content)}
                          >
                            <Copy />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Edit ${p.title}`}
                            onClick={() => {
                              setSelected({ ...p });
                              setTags(p.tags.join(", "));
                              setEditing(true);
                            }}
                          >
                            <Pencil />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`Delete ${p.title}`}
                            onClick={() => setRemove(p)}
                          >
                            <Trash2 />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>Page {page}</span>
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!data.has_more}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                  <ChevronRight />
                </Button>
              </div>
            </div>
          </>
        ) : !error ? (
          <Empty
            title={search ? "No matching prompts" : "Your library starts here"}
            text={
              search
                ? "Try a different title or clear your search."
                : "Save a prompt from the workspace to revisit it here."
            }
          />
        ) : (
          <Button className="m-6" onClick={() => setRefresh((x) => x + 1)}>
            Retry
          </Button>
        )}
      </section>
      {remove && (
        <section
          className="panel confirmation"
          role="alertdialog"
          aria-labelledby="delete-title"
        >
          <h2 id="delete-title">Delete “{remove.title}”?</h2>
          <p>This removes the saved prompt from your account.</p>
          <div className="button-row">
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => void deletePrompt()}
            >
              Delete prompt
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setRemove(undefined)}
            >
              Keep it
            </Button>
          </div>
        </section>
      )}
      {selected && (
        <section className="panel detail-panel">
          <div className="panel-header">
            <h2>{editing ? "Edit saved prompt" : selected.title}</h2>
            <Button variant="ghost" onClick={() => setSelected(undefined)}>
              Close
            </Button>
          </div>
          {editing ? (
            <form onSubmit={(e) => void save(e)}>
              <label htmlFor="edit-title">Title</label>
              <Input
                id="edit-title"
                required
                maxLength={200}
                value={selected.title}
                onChange={(e) =>
                  setSelected({ ...selected, title: e.target.value })
                }
              />
              <label htmlFor="edit-content">Prompt</label>
              <Textarea
                id="edit-content"
                required
                maxLength={50000}
                value={selected.content}
                onChange={(e) =>
                  setSelected({ ...selected, content: e.target.value })
                }
                className="history-content min-h-[240px]"
              />
              <label htmlFor="edit-tags">Tags (comma separated)</label>
              <Input
                id="edit-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
              />
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Save changes"}
              </Button>
            </form>
          ) : (
            <div className="detail-body">
              <Textarea
                aria-label="Saved prompt content"
                readOnly
                value={selected.content}
                className="history-content min-h-[240px]"
              />
              <div className="button-row">
                <Button onClick={() => void copy(selected.content)}>
                  <Copy />
                  Copy prompt
                </Button>
                <Button variant="outline" asChild>
                  <Link to="/workspace" state={{ content: selected.content }}>
                    Use as starting point <ArrowUpRight />
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </section>
      )}
    </>
  );
}
