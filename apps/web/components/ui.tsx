import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function Button({
  variant = "solid",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "solid" | "ghost" | "ember" | "line" }) {
  const styles = {
    solid: "bg-lime text-ink hover:bg-[#e7ff7a]",
    ghost: "bg-white/5 text-paper hover:bg-white/10",
    ember: "bg-ember text-white hover:bg-[#ff7354]",
    line: "border border-white/15 text-paper hover:border-lime hover:text-lime",
  }[variant];
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${styles} ${className}`}
      {...props}
    />
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block text-mute">{label}</span>
      {children}
    </label>
  );
}

const control = "w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm text-paper outline-none focus:border-lime";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={control} {...props} />;
}

export function Area(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${control} min-h-24`} {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={control} {...props} />;
}

export function Notice({ tone = "info", children }: { tone?: "info" | "bad" | "good"; children: ReactNode }) {
  const toneClass = tone === "bad" ? "border-ember/40 text-ember" : tone === "good" ? "border-lime/40 text-lime" : "border-white/10 text-mute";
  return <p className={`rounded-2xl border px-4 py-3 text-sm ${toneClass}`}>{children}</p>;
}

export function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-panel/80 p-5 shadow-card">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-serif text-2xl">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
