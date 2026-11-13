"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button, Field, Notice, Panel, Select, TextInput } from "@/components/ui";
import { api, Collection, fileUrl, NftItem, pollJob, Project, Report } from "@/lib/api";

export function Generator({ project }: { project: Project }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [current, setCurrent] = useState<string>("");
  const [items, setItems] = useState<NftItem[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function loadList() {
    const rows = await api<Collection[]>(`/api/projects/${project.id}/collections`);
    setCollections(rows);
    if (!current && rows[0]) setCurrent(rows[0].id);
  }

  async function loadOne(id: string) {
    const detail = await api<Collection & { items: NftItem[]; report: Report | null }>(`/api/collections/${id}`);
    setItems(detail.items || []);
    setReport(detail.report);
  }

  useEffect(() => {
    loadList().catch((err) => setError(err.message));
  }, [project.id]);

  useEffect(() => {
    if (current) loadOne(current).catch((err) => setError(err.message));
  }, [current]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    try {
      const created = await api<Collection>(`/api/projects/${project.id}/collections`, {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          supply: Number(form.get("supply")),
          seed: Number(form.get("seed")),
          mode: form.get("mode"),
          symbol: form.get("symbol") || "",
          description_template: form.get("description_template"),
          image_base_uri: form.get("image_base_uri") || "",
          metadata_schema: form.get("metadata_schema"),
          marketplace_profile: form.get("marketplace_profile"),
        }),
      });
      setCurrent(created.id);
      await loadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the collection");
    }
  }

  async function plan() {
    setBusy("Planning unique combinations");
    setError("");
    try {
      const result = await api<{ report: Report; items: NftItem[] }>(`/api/collections/${current}/plan`, { method: "POST" });
      setReport(result.report);
      setItems(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Planning failed");
    } finally {
      setBusy("");
    }
  }

  async function render() {
    setBusy("Rendering artwork");
    setError("");
    try {
      const job = await api<{ id: string }>(`/api/collections/${current}/render`, { method: "POST" });
      const finished = await pollJob(job.id);
      if (finished.status === "failed") throw new Error(finished.error || "Render failed");
      await loadOne(current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Render failed");
    } finally {
      setBusy("");
    }
  }

  async function regenerate(itemId: string) {
    setBusy("Rebuilding one token");
    try {
      await api(`/api/collections/${current}/items/${itemId}/regenerate`, { method: "POST" });
      await loadOne(current);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not regenerate");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-5">
      {error ? <Notice tone="bad">{error}</Notice> : null}
      {busy ? <Notice>{busy}</Notice> : null}
      <Panel title="Collection setup">
        <form onSubmit={create} className="grid gap-3 md:grid-cols-3">
          <Field label="Name"><TextInput name="name" required defaultValue={`${project.name} Drop`} /></Field>
          <Field label="Supply"><TextInput name="supply" type="number" defaultValue={12} /></Field>
          <Field label="Seed"><TextInput name="seed" type="number" defaultValue={7} /></Field>
          <Field label="Mode">
            <Select name="mode" defaultValue="weighted">
              <option value="weighted">Weighted random</option>
              <option value="exact">Exact counts</option>
            </Select>
          </Field>
          <Field label="Schema">
            <Select name="metadata_schema" defaultValue="erc721">
              <option value="erc721">ERC-721</option>
              <option value="metaplex">Metaplex</option>
            </Select>
          </Field>
          <Field label="Marketplace">
            <Select name="marketplace_profile" defaultValue="opensea">
              <option value="opensea">OpenSea</option>
              <option value="zora">Zora</option>
              <option value="metaplex">Metaplex</option>
              <option value="generic">Generic</option>
            </Select>
          </Field>
          <Field label="Symbol"><TextInput name="symbol" defaultValue="NFT" /></Field>
          <Field label="Description template"><TextInput name="description_template" defaultValue="{collection} #{token_id} — {trait_list}" /></Field>
          <Field label="Image base URI"><TextInput name="image_base_uri" placeholder="ipfs://CID/{token_id}.png" /></Field>
          <div className="md:col-span-3"><Button type="submit">Create collection</Button></div>
        </form>
        {collections.length ? (
          <div className="mt-4">
            <Select value={current} onChange={(event) => setCurrent(event.target.value)}>
              {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name} · {collection.supply} · {collection.status}</option>)}
            </Select>
          </div>
        ) : null}
        <div className="mt-4 flex gap-2">
          <Button disabled={!current || !!busy} onClick={plan}>Plan combinations</Button>
          <Button variant="ember" disabled={!current || !!busy} onClick={render}>Render images</Button>
        </div>
      </Panel>
      {report?.distribution?.length ? (
        <Panel title="Rarity">
          <div className="grid gap-4 md:grid-cols-2">
            {report.distribution.map((layer) => (
              <div key={layer.name}>
                <h3 className="mb-2 font-serif text-xl">{layer.name}</h3>
                {layer.traits.map((trait) => (
                  <div key={trait.name} className="mb-2">
                    <div className="flex justify-between text-xs text-mute"><span>{trait.name}</span><span>{trait.count} · {trait.percent}% / target {trait.target_percent}%</span></div>
                    <div className="mt-1 h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-purple" style={{ width: `${Math.min(trait.percent, 100)}%` }} /></div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
      <Panel title="Tokens">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {items.map((item) => (
            <article key={item.id} className="rounded-2xl border border-white/10 p-2">
              {item.thumb_url ? <img src={fileUrl(item.thumb_url)} alt="" className="aspect-square w-full rounded-xl object-cover" /> : <div className="grid aspect-square place-items-center rounded-xl bg-black/40 text-xs text-mute">Not rendered</div>}
              <p className="mt-2 text-sm">#{item.token_id}</p>
              <p className="text-xs text-mute">{item.attributes.map((attribute) => attribute.value).join(" · ")}</p>
              <button className="mt-2 text-xs text-purple" onClick={() => regenerate(item.id)}>Regenerate this token</button>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
