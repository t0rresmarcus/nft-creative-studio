"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Field, Notice, Panel, TextInput } from "@/components/ui";
import { api, currentUser, User } from "@/lib/api";

type Account = {
  user: User;
  plans: Record<string, { label: string; projects: number; supply: number; credits: number; price: number; blurb: string }>;
  usage: { projects: number; project_limit: number; supply_limit: number; credits: number };
  events: { kind: string; units: number; detail: string; created_at: string }[];
};

export default function AccountPage() {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const data = await api<Account>("/api/account");
    localStorage.setItem("nft_user", JSON.stringify(data.user));
    setAccount(data);
  }

  useEffect(() => {
    if (!currentUser()) {
      router.replace("/login");
      return;
    }
    load().catch((err) => setError(err.message));
  }, [router]);

  async function switchPlan(plan: string) {
    setError("");
    try {
      await api("/api/account/plan", { method: "POST", body: JSON.stringify({ plan }) });
      setMessage(`Plan set to ${plan}. Credits were reset to that plan's included amount.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change plan");
    }
  }

  async function saveIpfs(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await api("/api/account/ipfs", { method: "PUT", body: JSON.stringify({ pinata_jwt: form.get("jwt") || "" }) });
    setMessage("Pinning key saved on this server, encrypted with the server secret.");
    await load();
  }

  if (!account) return <main className="p-10 text-mute">Loading account</main>;

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-6 py-8">
      <header>
        <p className="text-sm tracking-[0.18em] text-purple">ACCOUNT</p>
        <h1 className="font-serif text-4xl">{account.user.name}</h1>
        <p className="text-mute">{account.user.email}</p>
      </header>
      {error ? <Notice tone="bad">{error}</Notice> : null}
      {message ? <Notice tone="good">{message}</Notice> : null}
      <Panel title="Usage">
        <p className="text-sm text-mute">
          {account.usage.projects} / {account.usage.project_limit} projects · up to {account.usage.supply_limit} NFTs per collection · {account.usage.credits} AI credits
        </p>
        <ul className="mt-4 space-y-2 text-sm text-mute">
          {account.events.map((event, index) => (
            <li key={`${event.created_at}-${index}`}>{event.created_at.slice(0, 16)} · {event.kind} · {event.detail || event.units}</li>
          ))}
        </ul>
      </Panel>
      <div className="grid gap-4 md:grid-cols-2">
        {Object.entries(account.plans).map(([id, plan]) => (
          <article key={id} className={`rounded-3xl border p-5 ${account.user.plan === id ? "border-purple" : "border-white/10"}`}>
            <h2 className="font-serif text-2xl">{plan.label}</h2>
            <p className="mt-1 text-sm text-mute">{plan.blurb}</p>
            <p className="mt-3 text-sm">{plan.projects} projects · {plan.supply} supply · {plan.credits} credits · ${plan.price}/mo</p>
            <Button className="mt-4" variant={account.user.plan === id ? "line" : "solid"} onClick={() => switchPlan(id)}>
              {account.user.plan === id ? "Current plan" : "Use this plan"}
            </Button>
          </article>
        ))}
      </div>
      <Panel title="IPFS pinning">
        <p className="mb-4 text-sm text-mute">
          {account.user.ipfs_configured ? "A Pinata JWT is saved." : "Without a key, uploads are content-addressed on this server so you can verify the bytes. Add a Pinata JWT to pin to IPFS."}
        </p>
        <form onSubmit={saveIpfs} className="flex gap-3">
          <Field label="Pinata JWT">
            <TextInput name="jwt" type="password" placeholder="Paste a JWT" />
          </Field>
          <Button type="submit" className="mt-6">Save</Button>
        </form>
      </Panel>
    </main>
  );
}
