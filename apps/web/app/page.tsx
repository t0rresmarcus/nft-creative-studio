import Link from "next/link";

const modules = [
  ["Editor", "Crop, color, layers, undo, and transparent PNG export."],
  ["Traits", "Layer order, weights, exact counts, and compatibility rules."],
  ["Generator", "Seeded unique combinations, with invalid pairs refused up front."],
  ["Automation", "Save a recipe and run it across a folder, with a dry run first."],
  ["Metadata", "ERC-721 and Metaplex JSON, plus a spreadsheet of the same tokens."],
  ["Publishing", "Validation report, ZIP, and optional Pinata pinning."],
];

export default function HomePage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="flex items-center justify-between">
        <p className="text-sm tracking-[0.2em] text-lime">NFT CREATIVE STUDIO</p>
        <div className="flex gap-2">
          <Link href="/login" className="rounded-full px-4 py-2 text-sm text-mute hover:text-paper">
            Sign in
          </Link>
          <Link href="/register" className="rounded-full bg-lime px-4 py-2 text-sm font-medium text-ink">
            Open the studio
          </Link>
        </div>
      </header>
      <section className="grid items-end gap-10 py-20 md:grid-cols-[1.3fr_0.7fr]">
        <div>
          <h1 className="font-serif text-5xl leading-[1.05] md:text-7xl">From raw frames to a mint-ready collection.</h1>
          <p className="mt-6 max-w-xl text-lg text-mute">
            One workspace for the edit, the trait stack, the rarity rules, the metadata, and the export. Invalid combinations are blocked while the collection is planned, not after you have rendered a thousand files.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/register" className="rounded-full bg-lime px-5 py-3 text-sm font-medium text-ink">
              Start a project
            </Link>
            <Link href="/login" className="rounded-full border border-white/15 px-5 py-3 text-sm">
              Use the demo project
            </Link>
          </div>
        </div>
        <ol className="space-y-3 rounded-3xl border border-white/10 bg-panel/70 p-5">
          {["Create the project", "Upload or draw the layers", "Set weights and rules", "Plan, then render", "Validate and export"].map((step, index) => (
            <li key={step} className="flex items-baseline gap-4 border-b border-white/5 pb-3 last:border-0 last:pb-0">
              <span className="font-serif text-3xl text-lime">{index + 1}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </section>
      <section className="grid gap-4 md:grid-cols-3">
        {modules.map(([title, copy]) => (
          <article key={title} className="rounded-3xl border border-white/10 bg-black/20 p-5">
            <h2 className="font-serif text-2xl">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-mute">{copy}</p>
          </article>
        ))}
      </section>
      <p className="mt-10 text-sm text-mute">
        Demo account <span className="text-paper">demo@nftstudio.local</span> / <span className="text-paper">demo-studio-123</span>. The sample project is called Signal Portraits.
      </p>
    </main>
  );
}
