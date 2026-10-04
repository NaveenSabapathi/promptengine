import {
  LoaderCircle,
  AlertCircle,
  ArrowUpRight,
  Terminal,
} from "lucide-react";
import { Link } from "react-router-dom";
export function Brand() {
  return (
    <Link to="/" className="brand">
      <span className="brand-mark">
        <Terminal size={19} />
      </span>
      PromptEngine<span className="brand-beta">BETA</span>
    </Link>
  );
}
export function Busy({ text = "Loading your workspace…" }: { text?: string }) {
  return (
    <div role="status" className="loading">
      <LoaderCircle className="animate-spin" size={22} />
      {text}
    </div>
  );
}
export function Notice({
  error,
  message,
}: {
  error?: string;
  message?: string;
}) {
  return error ? (
    <div role="alert" className="notice error">
      <AlertCircle size={18} />
      {error}
    </div>
  ) : message ? (
    <div role="status" className="notice success">
      {message}
    </div>
  ) : null;
}
export function Heading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="page-heading">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  );
}
export function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <ArrowUpRight size={25} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
