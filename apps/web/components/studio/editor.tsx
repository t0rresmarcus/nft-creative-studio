"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Field, Notice, Panel, TextInput } from "@/components/ui";
import { api, Asset, fileUrl, Project } from "@/lib/api";

type Snapshot = {
  brightness: number;
  contrast: number;
  saturation: number;
  rotation: number;
  crop: { x: number; y: number; width: number; height: number } | null;
  resizeW: number;
  resizeH: number;
};

export function LayerCanvas({ url }: { url: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = host.current;
    if (!container) return;
    let cancelled = false;
    let stage: { destroy: () => void } | null = null;
    (async () => {
      const Konva = (await import("konva")).default;
      if (cancelled) return;
      const nextStage = new Konva.Stage({ container, width: 560, height: 420 });
      stage = nextStage;
      const layer = new Konva.Layer();
      nextStage.add(layer);
      const element = new window.Image();
      element.crossOrigin = "anonymous";
      element.onload = () => {
        if (cancelled) return;
        const width = Math.min(480, element.width);
        const height = Math.min(360, (element.height / element.width) * width);
        const node = new Konva.Image({ image: element, x: 40, y: 30, width, height, draggable: true });
        const transformer = new Konva.Transformer({ rotateEnabled: true });
        layer.add(node);
        layer.add(transformer);
        transformer.nodes([node]);
        layer.draw();
      };
      element.src = url;
    })();
    return () => {
      cancelled = true;
      stage?.destroy();
      container.innerHTML = "";
    };
  }, [url]);

  return <div ref={host} className="h-[420px] w-[560px]" />;
}

export function Editor({ project }: { project: Project }) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [asset, setAsset] = useState<Asset | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [future, setFuture] = useState<Snapshot[]>([]);
  const [state, setState] = useState<Snapshot>({ brightness: 1, contrast: 1, saturation: 1, rotation: 0, crop: null, resizeW: project.canvas_width, resizeH: project.canvas_height });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const drag = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    api<Asset[]>(`/api/projects/${project.id}/assets`).then((rows) => {
      setAssets(rows);
      setAsset(rows[0] || null);
    }).catch((err) => setError(err.message));
  }, [project.id]);

  function update(partial: Partial<Snapshot>) {
    setHistory((current) => [...current, state]);
    setFuture([]);
    setState((current) => ({ ...current, ...partial }));
  }

  function operations() {
    const ops: { type: string; params: Record<string, unknown> }[] = [];
    if (state.crop) ops.push({ type: "crop", params: state.crop });
    if (state.rotation) ops.push({ type: "rotate", params: { degrees: state.rotation } });
    ops.push({ type: "resize", params: { width: state.resizeW, height: state.resizeH, fit: "contain" } });
    if (state.brightness !== 1) ops.push({ type: "brightness", params: { factor: state.brightness } });
    if (state.contrast !== 1) ops.push({ type: "contrast", params: { factor: state.contrast } });
    if (state.saturation !== 1) ops.push({ type: "saturation", params: { factor: state.saturation } });
    return ops;
  }

  async function apply() {
    if (!asset) return;
    setError("");
    try {
      const saved = await api<Asset>(`/api/assets/${asset.id}/render`, {
        method: "POST",
        body: JSON.stringify({ operations: operations(), layers: [] }),
      });
      setMessage(`Saved ${saved.original_name}. The original file is unchanged.`);
      const rows = await api<Asset[]>(`/api/projects/${project.id}/assets`);
      setAssets(rows);
      setAsset(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the edit");
    }
  }

  async function tool(path: string, body: unknown) {
    if (!asset) return;
    setError("");
    try {
      const result = await api<Asset | { asset: Asset }>(path, { method: "POST", body: JSON.stringify(body) });
      const saved = "asset" in result ? result.asset : result;
      setAsset(saved);
      setMessage("A new version was saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tool failed");
    }
  }

  const filter = `brightness(${state.brightness}) contrast(${state.contrast}) saturate(${state.saturation})`;

  return (
    <div className="grid gap-5 xl:grid-cols-[220px_1fr_280px]">
      <Panel title="Files">
        <div className="max-h-[640px] space-y-2 overflow-auto">
          {assets.map((item) => (
            <button key={item.id} className={`block w-full rounded-xl text-left text-xs ${asset?.id === item.id ? "text-purple" : "text-mute"}`} onClick={() => setAsset(item)}>
              {item.original_name}
            </button>
          ))}
        </div>
      </Panel>
      <Panel title="Canvas">
        {error ? <div className="mb-3"><Notice tone="bad">{error}</Notice></div> : null}
        {message ? <div className="mb-3"><Notice tone="good">{message}</Notice></div> : null}
        {asset ? (
          <div
            className="relative overflow-hidden rounded-2xl bg-[linear-gradient(45deg,#222_25%,transparent_25%),linear-gradient(-45deg,#222_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#222_75%),linear-gradient(-45deg,transparent_75%,#222_75%)] bg-[length:20px_20px] bg-[position:0_0,0_10px,10px_-10px,-10px_0]"
            onMouseDown={(event) => { drag.current = { x: event.nativeEvent.offsetX, y: event.nativeEvent.offsetY }; }}
            onMouseUp={(event) => {
              if (!drag.current || !asset) return;
              const scale = Math.min(640 / asset.width, 1);
              const x = Math.round(Math.min(drag.current.x, event.nativeEvent.offsetX) / scale);
              const y = Math.round(Math.min(drag.current.y, event.nativeEvent.offsetY) / scale);
              const width = Math.round(Math.abs(event.nativeEvent.offsetX - drag.current.x) / scale);
              const height = Math.round(Math.abs(event.nativeEvent.offsetY - drag.current.y) / scale);
              if (width > 4 && height > 4) update({ crop: { x, y, width, height } });
              drag.current = null;
            }}
          >
            <img src={fileUrl(asset.url)} alt="" style={{ filter, transform: `rotate(${state.rotation}deg)`, maxHeight: 640 }} className="mx-auto max-w-full" />
          </div>
        ) : <Notice>Upload an image in the library first.</Notice>}
        {asset ? <div className="mt-4 overflow-hidden rounded-2xl bg-black/40"><LayerCanvas url={fileUrl(asset.url)} /></div> : null}
        <p className="mt-3 text-xs text-mute">Drag on the preview to set a crop. The Konva stage below is for direct rotate and scale inspection. Saving runs the same steps on the server so the file matches the recipe.</p>
      </Panel>
      <Panel title="Adjust">
        <div className="space-y-3 text-sm">
          <label className="block text-mute">Brightness {state.brightness.toFixed(2)}
            <input className="w-full" type="range" min={0.4} max={1.8} step={0.02} value={state.brightness} onChange={(event) => update({ brightness: Number(event.target.value) })} />
          </label>
          <label className="block text-mute">Contrast {state.contrast.toFixed(2)}
            <input className="w-full" type="range" min={0.4} max={1.8} step={0.02} value={state.contrast} onChange={(event) => update({ contrast: Number(event.target.value) })} />
          </label>
          <label className="block text-mute">Saturation {state.saturation.toFixed(2)}
            <input className="w-full" type="range" min={0} max={2} step={0.02} value={state.saturation} onChange={(event) => update({ saturation: Number(event.target.value) })} />
          </label>
          <label className="block text-mute">Rotate {state.rotation}°
            <input className="w-full" type="range" min={-180} max={180} value={state.rotation} onChange={(event) => update({ rotation: Number(event.target.value) })} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Width"><TextInput type="number" value={state.resizeW} onChange={(event) => update({ resizeW: Number(event.target.value) })} /></Field>
            <Field label="Height"><TextInput type="number" value={state.resizeH} onChange={(event) => update({ resizeH: Number(event.target.value) })} /></Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="line" onClick={() => { const previous = history[history.length - 1]; if (!previous) return; setFuture((items) => [state, ...items]); setHistory((items) => items.slice(0, -1)); setState(previous); }}>Undo</Button>
            <Button variant="line" onClick={() => { const next = future[0]; if (!next) return; setHistory((items) => [...items, state]); setFuture((items) => items.slice(1)); setState(next); }}>Redo</Button>
            <Button onClick={apply}>Save version</Button>
          </div>
          <Button variant="ghost" onClick={() => asset && tool(`/api/assets/${asset.id}/remove-background`, { tolerance: 32, mode: "corner" })}>Remove background</Button>
          <Button variant="ghost" onClick={() => asset && tool(`/api/assets/${asset.id}/enhance`, { scale: 2 })}>Enhance 2×</Button>
          <Button variant="ghost" onClick={() => asset && tool(`/api/assets/${asset.id}/variations`, { count: 3, seed: 5 })}>Make 3 variations</Button>
          {state.crop ? <p className="text-xs text-mute">Crop {state.crop.width}×{state.crop.height} at {state.crop.x},{state.crop.y}</p> : null}
        </div>
      </Panel>
    </div>
  );
}
