"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button, Field, Notice, TextInput } from "@/components/ui";
import { api, saveSession, User } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError("");
    try {
      const result = await api<{ token: string; user: User }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      saveSession(result.token, result.user);
      router.push("/studio");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <Link href="/" className="mb-8 text-sm tracking-[0.18em] text-lime">
        NFT CREATIVE STUDIO
      </Link>
      <h1 className="font-serif text-4xl">Sign in</h1>
      <p className="mt-2 text-sm text-mute">Demo: demo@nftstudio.local / demo-studio-123</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <Field label="Email">
          <TextInput name="email" type="email" required defaultValue="demo@nftstudio.local" />
        </Field>
        <Field label="Password">
          <TextInput name="password" type="password" required defaultValue="demo-studio-123" />
        </Field>
        {error ? <Notice tone="bad">{error}</Notice> : null}
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Signing in" : "Enter the studio"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-mute">
        New here? <Link href="/register" className="text-lime">Create an account</Link>
      </p>
    </main>
  );
}
