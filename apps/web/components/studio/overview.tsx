"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button, Field, Notice, Panel, Select, TextInput } from "@/components/ui";
import { api, Project } from "@/lib/api";

type Step = { id: string; label: string; done: boolean };
type Member = { id: string | null; email: string; name: string; role: string };
type Comment = { id: string; author: string; body: string; created_at: string };

export function Overview({ project, onProject }: { project: Project; onProject: (project: Project) => void }) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [error, setError] = useState("");

  async function load() {
    const [nextSteps, nextMembers, nextComments] = await Promise.all([
      api<Step[]>(`/api/projects/${project.id}/checklist`),
      api<Member[]>(`/api/projects/${project.id}/members`),
      api<Comment[]>(`/api/projects/${project.id}/comments`),
    ]);
    setSteps(nextSteps);
    setMembers(nextMembers);
    setComments(nextComments);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [project.id]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const updated = await api<Project>(`/api/projects/${project.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: form.get("name"),
        description: form.get("description"),
        license: form.get("license"),
        ai_disclosure: form.get("ai_disclosure"),
      }),
    });
    onProject(updated);
  }

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      await api(`/api/projects/${project.id}/members`, {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), role: form.get("role") }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that person");
    }
  }

  async function comment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api(`/api/projects/${project.id}/comments`, { method: "POST", body: JSON.stringify({ body: form.get("body") }) });
    (event.target as HTMLFormElement).reset();
    await load();
  }

  const done = steps.filter((step) => step.done).length;

  return (
    <div className="space-y-5">
      {error ? <Notice tone="bad">{error}</Notice> : null}
      <Panel title="Production path" action={<span className="text-sm text-mute">{done}/{steps.length}</span>}>
        <ol className="grid gap-2 md:grid-cols-2">
          {steps.map((step, index) => (
            <li key={step.id} className="flex items-center gap-3 rounded-2xl border border-white/10 px-3 py-2 text-sm">
              <span className={`grid h-7 w-7 place-items-center rounded-full text-xs ${step.done ? "bg-purple text-ink" : "bg-white/10 text-mute"}`}>{index + 1}</span>
              <span className={step.done ? "text-paper" : "text-mute"}>{step.label}</span>
            </li>
          ))}
        </ol>
      </Panel>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Project">
          <form onSubmit={save} className="space-y-3">
            <Field label="Name"><TextInput name="name" defaultValue={project.name} /></Field>
            <Field label="Description"><TextInput name="description" defaultValue={project.description} /></Field>
            <Field label="License">
              <Select name="license" defaultValue={project.license}>
                <option value="custom">Custom</option>
                <option value="cc0">CC0</option>
                <option value="cc-by">CC BY</option>
                <option value="commercial">Commercial</option>
              </Select>
            </Field>
            <Field label="AI disclosure"><TextInput name="ai_disclosure" defaultValue={project.ai_disclosure} placeholder="How AI was used, if at all" /></Field>
            <Button type="submit">Save</Button>
          </form>
        </Panel>
        <Panel title="People">
          <ul className="mb-4 space-y-2 text-sm">
            {members.map((member) => (
              <li key={member.email} className="flex justify-between rounded-xl bg-black/20 px-3 py-2">
                <span>{member.name} · {member.email}</span>
                <span className="text-mute">{member.role}</span>
              </li>
            ))}
          </ul>
          {project.role === "owner" ? (
            <form onSubmit={invite} className="grid gap-3">
              <Field label="Invite by email"><TextInput name="email" type="email" required /></Field>
              <Field label="Role">
                <Select name="role" defaultValue="editor">
                  <option value="editor">Editor</option>
                  <option value="reviewer">Reviewer</option>
                </Select>
              </Field>
              <Button type="submit" variant="line">Add</Button>
            </form>
          ) : <p className="text-sm text-mute">Only the owner can change roles.</p>}
        </Panel>
      </div>
      <Panel title="Notes">
        <ul className="mb-4 space-y-3">
          {comments.map((item) => (
            <li key={item.id} className="text-sm"><span className="text-purple">{item.author}</span> · {item.body}</li>
          ))}
        </ul>
        <form onSubmit={comment} className="flex gap-2">
          <TextInput name="body" required placeholder="Leave a note for the team" />
          <Button type="submit">Post</Button>
        </form>
      </Panel>
    </div>
  );
}
