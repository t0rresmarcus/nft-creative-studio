"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button, Field, Notice, Panel, Select, TextInput } from "@/components/ui";
import { api, Asset, fileUrl, pollJob, Project } from "@/lib/api";

type Operation = { type: string; params: Record<string, string | number>; when?: { field: string; op: string; value: string } };
type CatalogItem = { type: string; label: string; params: { name: string; kind: string; default?: string | number; options?: string[] }[] };
type Workflow = { id: string; name: string; description: string; operations: Operation[]; version: number };

export function Automate({ project }: { project: Project }) {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [ops, setOps] = useState<Operation[]>([]);
  const [outputs, setOutputs] = useState<Asset[]>([]);
  const [error, setError] = useState("");
  const [active, setActive] = useState<string>("");

  useEffect(() => {
    Promise.all([
      api<CatalogItem[]>("/api/operation-catalog"),
      api<Workflow[]>(`/api/projects/${project.id}/workflows`),
      api<Asset[]>(`/api/projects/${project.id}/assets`),
    ]).then(([nextCatalog, nextWorkflows, nextAssets]) => {
      setCatalog(nextCatalog);
      setWorkflows(nextWorkflows);
      setAssets(nextAssets);
      if (nextWorkflows[0]) {
        setActive(nextWorkflows[0].id);
        setOps(nextWorkflows[0].operations || []);
      }
    }).catch((err) => setError(err.message));
  }, [project.id]);

  function addOp(type: string) {
    const spec = catalog.find((item) => item.type === type);
    const params: Record<string, string | number> = {};
    spec?.params.forEach((param) => {
      if (param.default !== undefined) params[param.name] = param.default;
    });
    setOps((current) => [...current, { type, params }]);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = { name: form.get("name"), description: form.get("description") || "", operations: ops };
    const saved = active
      ? await api<Workflow>(`/api/workflows/${active}`, { method: "PATCH", body: JSON.stringify(body) })
      : await api<Workflow>(`/api/projects/${project.id}/workflows`, { method: "POST", body: JSON.stringify(body) });
    setActive(saved.id);
    setWorkflows(await api(`/api/projects/${project.id}/workflows`));
  }

  async function run(dryRun: boolean) {
    if (!active) return;
    setError("");
    try {
      const job = await api<{ id: string }>(`/api/workflows/${active}/run`, {
        method: "POST",
        body: JSON.stringify({ asset_ids: selected.length ? selected : assets.slice(0, 8).map((asset) => asset.id), seed: 11, dry_run: dryRun }),
      });
      const finished = await pollJob(job.id);
      if (finished.status === "failed") throw new Error(finished.error || "Batch failed");
      const ids = finished.result?.outputs?.map((output) => output.asset_id) || [];
      const all = await api<Asset[]>(`/api/projects/${project.id}/assets`);
      setAssets(all);
      setOutputs(all.filter((asset) => ids.includes(asset.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch failed");
    }
  }

  return (
    <div className="space-y-5">
      {error ? <Notice tone="bad">{error}</Notice> : null}
      <Panel title="Recipe">
        <div className="mb-4 flex flex-wrap gap-2">
          {catalog.map((item) => (
            <button key={item.type} className="rounded-full border border-white/10 px-3 py-1 text-xs text-mute hover:text-lime" onClick={() => addOp(item.type)}>{item.label}</button>
          ))}
        </div>
        <ol className="space-y-3">
          {ops.map((operation, index) => (
            <li key={`${operation.type}-${index}`} className="rounded-2xl border border-white/10 p-3 text-sm">
              <div className="mb-2 flex justify-between"><span>{operation.type}</span><button className="text-mute" onClick={() => setOps(ops.filter((_, item) => item !== index))}>Remove</button></div>
              <div className="grid gap-2 md:grid-cols-3">
                {Object.entries(operation.params).map(([name, value]) => (
                  <label key={name} className="text-xs text-mute">{name}
                    <input className="mt-1 w-full rounded-lg border border-white/10 bg-transparent px-2 py-1 text-paper" value={value} onChange={(event) => {
                      const next = [...ops];
                      const parsed = event.target.value === "" || Number.isNaN(Number(event.target.value)) ? event.target.value : Number(event.target.value);
                      next[index] = { ...operation, params: { ...operation.params, [name]: parsed } };
                      setOps(next);
                    }} />
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ol>
        <form onSubmit={save} className="mt-4 grid gap-3 md:grid-cols-2">
          <Field label="Recipe name"><TextInput name="name" required defaultValue={workflows.find((item) => item.id === active)?.name || "Batch recipe"} /></Field>
          <Field label="Notes"><TextInput name="description" defaultValue={workflows.find((item) => item.id === active)?.description || ""} /></Field>
          <div className="flex gap-2 md:col-span-2">
            <Button type="submit">{active ? "Update recipe" : "Save recipe"}</Button>
            <Button type="button" variant="line" onClick={() => run(true)}>Dry run 8</Button>
            <Button type="button" variant="ember" onClick={() => run(false)}>Run batch</Button>
          </div>
        </form>
        {workflows.length > 1 ? (
          <Select className="mt-4" value={active} onChange={(event) => {
            const next = workflows.find((item) => item.id === event.target.value);
            setActive(event.target.value);
            setOps(next?.operations || []);
          }}>
            {workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name} v{workflow.version}</option>)}
          </Select>
        ) : null}
      </Panel>
      <Panel title="Source images">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          {assets.filter((asset) => asset.kind !== "preview").slice(0, 24).map((asset) => (
            <button key={asset.id} onClick={() => setSelected((current) => current.includes(asset.id) ? current.filter((id) => id !== asset.id) : [...current, asset.id])} className={`overflow-hidden rounded-xl border ${selected.includes(asset.id) ? "border-lime" : "border-white/10"}`}>
              <img src={fileUrl(asset.thumb_url)} alt="" className="aspect-square w-full object-cover" />
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-mute">{selected.length ? `${selected.length} selected` : "None selected, so the run uses the first 8 images."} The same seed and source hash reproduce the same output.</p>
      </Panel>
      {outputs.length ? (
        <Panel title="Latest outputs">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {outputs.map((asset) => <img key={asset.id} src={fileUrl(asset.url)} alt={asset.original_name} className="rounded-xl" />)}
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
