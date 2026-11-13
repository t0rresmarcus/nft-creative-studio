"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button, Field, Notice, Panel, Select, TextInput } from "@/components/ui";
import { api, Category, fileUrl, Project, Rule } from "@/lib/api";

export function Traits({ project }: { project: Project }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState("");
  const [dragId, setDragId] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  async function load() {
    const graph = await api<{ categories: Category[]; rules: Rule[] }>(`/api/projects/${project.id}/traits`);
    setCategories(graph.categories);
    setRules(graph.rules);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [project.id]);

  async function addCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api(`/api/projects/${project.id}/categories`, {
      method: "POST",
      body: JSON.stringify({ name: form.get("name"), optional: form.get("optional") === "on" }),
    });
    (event.target as HTMLFormElement).reset();
    await load();
  }

  async function uploadTrait(categoryId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = new FormData();
    body.set("name", String(form.get("name")));
    body.set("weight", String(form.get("weight") || "1"));
    const file = form.get("file");
    if (!(file instanceof File) || !file.size) return;
    body.set("file", file);
    setError("");
    try {
      await api(`/api/categories/${categoryId}/traits`, { method: "POST", body });
      (event.target as HTMLFormElement).reset();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function patchTrait(id: string, payload: Record<string, unknown>) {
    await api(`/api/traits/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
    await load();
  }

  async function drop(targetId: string) {
    if (!dragId || dragId === targetId) return;
    const ids = categories.map((category) => category.id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(targetId);
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    await api(`/api/projects/${project.id}/categories/order`, { method: "POST", body: JSON.stringify({ ids }) });
    setDragId(null);
    await load();
  }

  async function addRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      await api(`/api/projects/${project.id}/rules`, {
        method: "POST",
        body: JSON.stringify({ rule_type: form.get("rule_type"), trait_a_id: form.get("a"), trait_b_id: form.get("b") }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the rule");
    }
  }

  const traits = categories.flatMap((category) => category.traits.map((trait) => ({ ...trait, category: category.name })));

  return (
    <div className="space-y-5">
      {error ? <Notice tone="bad">{error}</Notice> : null}
      <Panel
        title="Layers"
        action={
          <Button
            variant="line"
            onClick={async () => {
              setError("");
              try {
                await api(`/api/projects/${project.id}/traits/sample?replace=${categories.length ? "true" : "false"}`, { method: "POST" });
                await load();
              } catch (err) {
                setError(err instanceof Error ? err.message : "Could not load samples");
              }
            }}
          >
            {categories.length ? "Replace with sample layers" : "Load sample layers"}
          </Button>
        }
      >
        <p className="mb-4 text-sm text-mute">Bottom layers render first. Drag a layer onto another to reorder. Weights drive random generation. Exact counts, when set on every trait in a layer, drive exact-count generation.</p>
        <form onSubmit={addCategory} className="mb-4 flex flex-wrap items-end gap-3">
          <Field label="New layer"><TextInput name="name" required placeholder="Background" /></Field>
          <label className="mb-2 flex items-center gap-2 text-sm text-mute"><input name="optional" type="checkbox" /> Optional</label>
          <Button type="submit">Add layer</Button>
        </form>
        <div className="space-y-4">
          {categories.map((category, index) => (
            <article
              key={category.id}
              draggable
              onDragStart={() => setDragId(category.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => drop(category.id)}
              className="rounded-2xl border border-white/10 p-4"
            >
              <header className="mb-3 flex items-center justify-between">
                <h3 className="font-serif text-xl">{index + 1}. {category.name}</h3>
                <button className="text-xs text-mute" onClick={async () => { await api(`/api/categories/${category.id}`, { method: "DELETE" }); await load(); }}>Remove</button>
              </header>
              <div className="grid gap-3 md:grid-cols-3">
                {category.traits.map((trait) => (
                  <div key={trait.id} className="rounded-xl bg-black/30 p-3 text-sm">
                    {trait.url ? <img src={fileUrl(trait.url)} alt="" className="mb-2 aspect-square w-full rounded-lg object-cover" /> : null}
                    <p>{trait.name}</p>
                    <label className="mt-2 block text-xs text-mute">Weight
                      <input className="w-full" type="range" min={0.1} max={5} step={0.05} defaultValue={trait.weight} onMouseUp={(event) => patchTrait(trait.id, { weight: Number((event.target as HTMLInputElement).value) })} />
                    </label>
                    <label className="mt-2 block text-xs text-mute">Exact count
                      <input className="mt-1 w-full rounded-lg border border-white/10 bg-transparent px-2 py-1" type="number" placeholder="blank = use weight" defaultValue={trait.exact_count ?? ""} onBlur={(event) => {
                        const value = event.target.value;
                        patchTrait(trait.id, value === "" ? { clear_exact_count: true } : { exact_count: Number(value) });
                      }} />
                    </label>
                  </div>
                ))}
              </div>
              <form onSubmit={(event) => uploadTrait(category.id, event)} className="mt-3 flex flex-wrap items-end gap-2">
                <Field label="Trait name"><TextInput name="name" required /></Field>
                <Field label="Weight"><TextInput name="weight" type="number" step="0.1" defaultValue={1} /></Field>
                <Field label="Artwork"><input name="file" type="file" accept="image/*" required className="text-xs" /></Field>
                <Button type="submit" variant="line">Upload trait</Button>
              </form>
            </article>
          ))}
        </div>
      </Panel>
      <Panel title="Compatibility" action={<Button variant="ghost" onClick={async () => {
        const result = await api<{ asset: { url: string } }>(`/api/projects/${project.id}/traits/preview`, { method: "POST", body: JSON.stringify({ trait_ids: [] }) });
        setPreview(fileUrl(result.asset.url));
      }}>Preview a random mix</Button>}>
        {preview ? <img src={preview} alt="Combination preview" className="mb-4 h-48 rounded-2xl" /> : null}
        <ul className="mb-4 space-y-2 text-sm">
          {rules.map((rule) => {
            const left = traits.find((trait) => trait.id === rule.trait_a_id);
            const right = traits.find((trait) => trait.id === rule.trait_b_id);
            return (
              <li key={rule.id} className="flex justify-between rounded-xl bg-black/20 px-3 py-2">
                <span>{rule.rule_type === "exclude" ? "Exclude" : "Require"} {left?.name} → {right?.name}</span>
                <button className="text-mute" onClick={async () => { await api(`/api/rules/${rule.id}`, { method: "DELETE" }); await load(); }}>Remove</button>
              </li>
            );
          })}
        </ul>
        <form onSubmit={addRule} className="grid gap-3 md:grid-cols-4">
          <Field label="Rule">
            <Select name="rule_type" defaultValue="exclude">
              <option value="exclude">Cannot appear together</option>
              <option value="require">First requires second</option>
            </Select>
          </Field>
          <Field label="Trait A"><Select name="a">{traits.map((trait) => <option key={trait.id} value={trait.id}>{trait.category}: {trait.name}</option>)}</Select></Field>
          <Field label="Trait B"><Select name="b">{traits.map((trait) => <option key={trait.id} value={trait.id}>{trait.category}: {trait.name}</option>)}</Select></Field>
          <div className="self-end"><Button type="submit">Add rule</Button></div>
        </form>
      </Panel>
    </div>
  );
}
