"use client";

import { useEffect, useState } from "react";
import { Button, Notice, Panel } from "@/components/ui";
import { api, Asset, fileUrl, Project } from "@/lib/api";

export function Library({ project, onPick }: { project: Project; onPick?: (asset: Asset) => void }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [error, setError] = useState("");

  async function load() {
    setAssets(await api<Asset[]>(`/api/projects/${project.id}/assets`));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [project.id]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    const body = new FormData();
    Array.from(files).forEach((file) => body.append("files", file));
    setError("");
    try {
      await api(`/api/projects/${project.id}/assets`, { method: "POST", body });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  return (
    <Panel title="Library" action={<span className="text-sm text-mute">{assets.length} files</span>}>
      {error ? <div className="mb-4"><Notice tone="bad">{error}</Notice></div> : null}
      <label className="mb-5 flex cursor-pointer flex-col items-center justify-center rounded-3xl border border-dashed border-white/15 px-6 py-10 text-sm text-mute hover:border-lime">
        Drop images or click to upload. Originals are stored by SHA-256 and never overwritten.
        <input className="hidden" type="file" accept="image/*" multiple onChange={(event) => upload(event.target.files)} />
      </label>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {assets.map((asset) => (
          <button key={asset.id} type="button" onClick={() => onPick?.(asset)} className="overflow-hidden rounded-2xl border border-white/10 text-left">
            <img src={fileUrl(asset.thumb_url)} alt={asset.original_name} className="aspect-square w-full object-cover" />
            <span className="block px-3 py-2 text-xs text-mute">{asset.original_name}<br />{asset.width}×{asset.height} · {asset.kind}</span>
          </button>
        ))}
      </div>
    </Panel>
  );
}
