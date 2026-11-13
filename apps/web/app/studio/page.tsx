"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { Button, Field, Notice, Select, TextInput } from "@/components/ui";
import { api, currentUser, Project, User } from "@/lib/api";

export default function StudioHome() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const session = currentUser();
    if (!session || !localStorage.getItem("nft_token")) {
      router.replace("/login");
      return;
    }
    setUser(session);
    api<Project[]>("/api/projects").then(setProjects).catch((err) => setError(err.message));
  }, [router]);

  async function createProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      const project = await api<Project>("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description") || "",
          project_type: form.get("project_type"),
          canvas_width: Number(form.get("canvas_width") || 1024),
          canvas_height: Number(form.get("canvas_height") || 1024),
          license: form.get("license"),
        }),
      });
      router.push(`/studio/${project.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project");
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm tracking-[0.18em] text-lime">STUDIO</p>
          <h1 className="font-serif text-4xl">{user ? `${user.name}'s projects` : "Projects"}</h1>
        </div>
        <div className="flex gap-2 text-sm">
          <Link href="/account" className="rounded-full border border-white/10 px-4 py-2">
            {user ? `${user.plan} · ${user.credits} credits` : "Account"}
          </Link>
          <button
            className="rounded-full px-4 py-2 text-mute"
            onClick={() => {
              localStorage.clear();
              router.push("/");
            }}
          >
            Sign out
          </button>
        </div>
      </header>
      {error ? <div className="mt-6"><Notice tone="bad">{error}</Notice></div> : null}
      <div className="mt-8 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="grid gap-4 sm:grid-cols-2">
          {projects.length === 0 ? <Notice>No projects yet. Create one, or sign in as the demo artist.</Notice> : null}
          {projects.map((project) => (
            <Link key={project.id} href={`/studio/${project.id}`} className="rounded-3xl border border-white/10 bg-panel p-5 hover:border-lime/50">
              <p className="text-xs uppercase tracking-[0.16em] text-mute">{project.project_type}</p>
              <h2 className="mt-2 font-serif text-3xl">{project.name}</h2>
              <p className="mt-3 text-sm text-mute">{project.asset_count} files · {project.collection_count} collections · {project.role}</p>
            </Link>
          ))}
        </div>
        <form onSubmit={createProject} className="h-fit space-y-4 rounded-3xl border border-white/10 bg-panel p-5">
          <h2 className="font-serif text-2xl">New project</h2>
          <Field label="Name"><TextInput name="name" required placeholder="Signal Portraits" /></Field>
          <Field label="Description"><TextInput name="description" placeholder="What this collection is" /></Field>
          <Field label="Type">
            <Select name="project_type" defaultValue="generative">
              <option value="generative">Generative collection</option>
              <option value="photo">Photo batch</option>
              <option value="edition">Edition</option>
              <option value="single">Single artwork</option>
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Width"><TextInput name="canvas_width" type="number" defaultValue={1024} /></Field>
            <Field label="Height"><TextInput name="canvas_height" type="number" defaultValue={1024} /></Field>
          </div>
          <Field label="License">
            <Select name="license" defaultValue="custom">
              <option value="custom">Custom</option>
              <option value="cc0">CC0</option>
              <option value="cc-by">CC BY</option>
              <option value="commercial">Commercial</option>
            </Select>
          </Field>
          <Button type="submit">Create project</Button>
        </form>
      </div>
    </main>
  );
}
