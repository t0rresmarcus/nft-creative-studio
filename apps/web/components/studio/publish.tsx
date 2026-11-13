"use client";

import { useEffect, useState } from "react";
import { Button, Notice, Panel } from "@/components/ui";
import { api, Collection, downloadBlob, NftItem, pollJob, Project, Report } from "@/lib/api";

export function Publish({ project }: { project: Project }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [current, setCurrent] = useState("");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [items, setItems] = useState<NftItem[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    api<Collection[]>(`/api/projects/${project.id}/collections`).then((list) => {
      setCollections(list);
      if (list[0]) setCurrent(list[0].id);
    }).catch((err) => setError(err.message));
  }, [project.id]);

  useEffect(() => {
    if (!current) return;
    Promise.all([
      api<Record<string, unknown>[]>(`/api/collections/${current}/metadata`),
      api<Report>(`/api/collections/${current}/report`),
      api<{ items: NftItem[] }>(`/api/collections/${current}`),
    ]).then(([metadata, nextReport, detail]) => {
      setRows(metadata);
      setReport(nextReport);
      setItems(detail.items || []);
    }).catch((err) => setError(err.message));
  }, [current]);

  async function download(path: string, filename: string, force = false) {
    setError("");
    try {
      const blob = await api<Blob>(`${path}${force ? "?force=true" : ""}`);
      downloadBlob(blob, filename);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  async function pin() {
    setError("");
    setNote("Uploading and verifying files");
    try {
      const job = await api<{ id: string }>(`/api/collections/${current}/ipfs`, { method: "POST" });
      const finished = await pollJob(job.id);
      if (finished.status === "failed") throw new Error(finished.error || "Upload failed");
      const count = Object.keys(finished.result?.cids || {}).length;
      setNote(finished.result?.cids ? `Stored ${count} tokens. Metadata image URIs were updated.` : "Upload finished");
      setReport(await api(`/api/collections/${current}/report`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  async function decide(itemId: string, status: string) {
    await api(`/api/items/${itemId}/decision`, { method: "POST", body: JSON.stringify({ status }) });
    setNote(`Token marked ${status}`);
  }

  return (
    <div className="space-y-5">
      {error ? <Notice tone="bad">{error}</Notice> : null}
      {note ? <Notice tone="good">{note}</Notice> : null}
      <Panel title="Metadata">
        {collections.length ? (
          <select className="mb-4 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm" value={current} onChange={(event) => setCurrent(event.target.value)}>
            {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
          </select>
        ) : <p className="text-sm text-mute">Generate a collection first.</p>}
        <div className="overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-mute"><tr><th className="py-2">Token</th><th>Name</th><th>Image</th><th>Attributes</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={String(row.token_id)} className="border-t border-white/5">
                  <td className="py-2">{String(row.token_id)}</td>
                  <td>{String(row.name || "")}</td>
                  <td className="max-w-xs truncate text-mute">{String(row.image || "")}</td>
                  <td className="text-mute">{Array.isArray(row.attributes) ? (row.attributes as { value: string }[]).map((item) => item.value).join(", ") : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="line" disabled={!current} onClick={() => download(`/api/collections/${current}/metadata.csv`, "metadata.csv")}>Download CSV</Button>
        </div>
      </Panel>
      <Panel title="Validation">
        <p className="mb-3 text-sm">{report ? `Status: ${report.status}. ${report.rendered || 0} rendered.` : "No report yet."}</p>
        <ul className="space-y-2 text-sm">
          {report?.blocking.map((item, index) => <li key={`b${index}`} className="text-ember">{item.message}</li>)}
          {report?.warnings.slice(0, 8).map((item, index) => <li key={`w${index}`} className="text-mute">{item.message}</li>)}
          {report?.near_duplicates.slice(0, 8).map((pair) => <li key={`${pair.token_a}-${pair.token_b}`} className="text-mute">Tokens {pair.token_a} and {pair.token_b} are visually close (distance {pair.distance}).</li>)}
        </ul>
      </Panel>
      <Panel title="Export">
        <div className="flex flex-wrap gap-2">
          <Button disabled={!current} onClick={() => download(`/api/collections/${current}/export`, `${project.name}.zip`)}>Download ZIP</Button>
          <Button variant="line" disabled={!current} onClick={() => download(`/api/collections/${current}/export`, `${project.name}.zip`, true)}>Export anyway</Button>
          <Button variant="ember" disabled={!current} onClick={pin}>Upload and verify</Button>
        </div>
        <p className="mt-3 text-sm text-mute">The ZIP contains images, JSON metadata, CSV, a provenance file, and the validation report. Upload uses Pinata when a key is saved, otherwise a local content address you can fetch back.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {items.slice(0, 8).map((item) => (
            <div key={item.id} className="rounded-full border border-white/10 px-3 py-1 text-xs">
              #{item.token_id}
              <button className="ml-2 text-purple" onClick={() => decide(item.id, "approved")}>Approve</button>
              <button className="ml-2 text-ember" onClick={() => decide(item.id, "rejected")}>Reject</button>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
