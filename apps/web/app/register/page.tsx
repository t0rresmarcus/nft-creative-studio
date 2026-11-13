"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Button, Field, Notice, TextInput } from "@/components/ui";
import { api, saveSession, User } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setPending(true);
    setError("");
    try {
      const result = await api<{ token: string; user: User }>("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ name: form.get("name"), email: form.get("email"), password: form.get("password") }),
      });
      saveSession(result.token, result.user);
      router.push("/studio");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the account");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <Link href="/" className="mb-8 text-sm tracking-[0.18em] text-purple">
        NFT CREATIVE STUDIO
      </Link>
      <h1 className="font-serif text-4xl">Create an account</h1>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <Field label="Name">
          <TextInput name="name" required />
        </Field>
        <Field label="Email">
          <TextInput name="email" type="email" required />
        </Field>
        <Field label="Password">
          <TextInput name="password" type="password" minLength={8} required />
        </Field>
        {error ? <Notice tone="bad">{error}</Notice> : null}
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? "Creating" : "Create account"}
        </Button>
      </form>
      <p className="mt-6 text-sm text-mute">
        Already registered? <Link href="/login" className="text-purple">Sign in</Link>
      </p>
    </main>
  );
}
