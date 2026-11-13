"use client";

import { useEffect, useState } from "react";
import { Button, Field, Notice, Panel, TextInput } from "@/components/ui";
import { api, Asset, fileUrl, Project } from "@/lib/api";

export function AiStudio({ project }: { project: Project }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [asset, setAsset] = useState<Asset | null>(null);
  const [results, setResults] = useState<Asset[]>([]);
  const [error, setError] = useState("");
  const [method, setMethod] = useState("");

  useEffect(() => {
    api<Asset[]>(`/api/projects/${project.id}/assets`).then((rows) => {
      setAssets(rows);
      setAsset(rows[0] || null);
    }).catch((err) => setError(err.message));
  }, [project.id]);

  async function run(path: string, body: unknown) {
    if (!asset) return;
    setError("");
    try {
      const result = await api<Asset | Asset[] | { asset: Asset; method?: string }>(path, { method: "POST", body: JSON.stringify(body) });
      if (Array.isArray(result)) {
        setResults(result);
        setMethod("variations");
      } else if ("asset" in result) {
        setResults([result.asset]);
        setMethod(result.method || "done");
      } else {
        setResults([result]);
        setMethod("done");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The tool failed");
    }
  }

  return (
    <Panel title="AI studio">
      <p className="mb-4 text-sm text-mute">
        Background removal uses a corner flood fill, or a connected model service when AI_ENDPOINT or rembg is available. Enhancement is a sharp, contrast, and upscale pass and spends one credit. Object removal fills a rectangle from the nearest edge pixels.
      </p>
      {error ? <div className="mb-4"><Notice tone="bad">{error}</Notice></div> : null}
      <div className="grid gap-5 lg:grid-cols-[240px_1fr]">
        <div className="max-h-96 space-y-1 overflow-auto text-sm">
          {assets.map((item) => (
            <button key={item.id} className={`block w-full truncate text-left ${asset?.id === item.id ? "text-lime" : "text-mute"}`} onClick={() => setAsset(item)}>{item.original_name}</button>
          ))}
        </div>
        <div>
          {asset ? <img src={fileUrl(asset.url)} alt="" className="mb-4 max-h-72 rounded-2xl" /> : null}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => run(`/api/assets/${asset?.id}/remove-background`, { mode: "corner", tolerance: 36 })}>Cut background</Button>
            <Button variant="line" onClick={() => run(`/api/assets/${asset?.id}/remove-background`, { mode: "corner", tolerance: 36, replacement_color: "#d6ff3f" })}>Replace with lime</Button>
            <Button variant="line" onClick={() => run(`/api/assets/${asset?.id}/remove-background`, { mode: "ai", tolerance: 28 })}>AI cut</Button>
            <Button variant="ember" onClick={() => run(`/api/assets/${asset?.id}/enhance`, { scale: 2 })}>Enhance</Button>
            <Button variant="ghost" onClick={() => run(`/api/assets/${asset?.id}/inpaint`, { x: 8, y: 8, width: 48, height: 48 })}>Remove corner box</Button>
            <Button variant="ghost" onClick={() => run(`/api/assets/${asset?.id}/variations`, { count: 4, seed: 21 })}>Variations</Button>
          </div>
          {method ? <p className="mt-3 text-xs text-mute">Method: {method}</p> : null}
          <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
            {results.map((item) => <img key={item.id} src={fileUrl(item.url)} alt={item.original_name} className="rounded-xl" />)}
          </div>
          <form className="mt-4" onSubmit={(event) => event.preventDefault()}>
            <Field label="Selected file"><TextInput readOnly value={asset?.original_name || ""} /></Field>
          </form>
        </div>
      </div>
    </Panel>
  );
}
