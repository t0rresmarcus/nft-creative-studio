"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AiStudio } from "@/components/studio/ai-studio";
import { Automate } from "@/components/studio/automate";
import { Editor } from "@/components/studio/editor";
import { Generator } from "@/components/studio/generator";
import { Library } from "@/components/studio/library";
import { Overview } from "@/components/studio/overview";
import { Publish } from "@/components/studio/publish";
import { Traits } from "@/components/studio/traits";
import { api, Project } from "@/lib/api";

const NAV = [
  ["overview", "Overview"],
  ["library", "Library"],
  ["editor", "Editor"],
  ["traits", "Traits"],
  ["generate", "Generate"],
  ["automate", "Automate"],
  ["publish", "Metadata & export"],
  ["ai", "AI"],
] as const;

export function Workspace() {
  const params = useParams<{ projectId: string }>();
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<(typeof NAV)[number][0]>("overview");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!localStorage.getItem("nft_token")) {
      router.replace("/login");
      return;
    }
    api<Project>(`/api/projects/${params.projectId}`).then(setProject).catch((err) => setError(err.message));
  }, [params.projectId, router]);

  if (error) return <main className="p-10 text-ember">{error}</main>;
  if (!project) return <main className="p-10 text-mute">Opening project</main>;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      <aside className="border-b border-white/10 p-5 md:border-b-0 md:border-r">
        <Link href="/studio" className="text-xs tracking-[0.18em] text-lime">STUDIO</Link>
        <h1 className="mt-3 font-serif text-3xl leading-none">{project.name}</h1>
        <p className="mt-2 text-xs uppercase tracking-[0.14em] text-mute">{project.project_type} · {project.canvas_width}×{project.canvas_height}</p>
        <nav className="mt-6 flex gap-2 overflow-auto md:block md:space-y-1">
          {NAV.map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)} className={`block rounded-full px-3 py-2 text-left text-sm md:w-full ${tab === id ? "bg-lime text-ink" : "text-mute hover:text-paper"}`}>
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="p-5 md:p-8">
        {tab === "overview" ? <Overview project={project} onProject={setProject} /> : null}
        {tab === "library" ? <Library project={project} /> : null}
        {tab === "editor" ? <Editor project={project} /> : null}
        {tab === "traits" ? <Traits project={project} /> : null}
        {tab === "generate" ? <Generator project={project} /> : null}
        {tab === "automate" ? <Automate project={project} /> : null}
        {tab === "publish" ? <Publish project={project} /> : null}
        {tab === "ai" ? <AiStudio project={project} /> : null}
      </main>
    </div>
  );
}
