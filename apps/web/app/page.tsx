import Link from "next/link";
import Image from "next/image";
import { Crop, Dices, FileJson, Layers, PackageCheck, Workflow, type LucideIcon } from "lucide-react";

const heroes = [
  { src: "/hero/fox-rooftop.jpg", alt: "Illustrated fox seated on a neon rooftop" },
  { src: "/hero/neon-portrait.jpg", alt: "Neon portrait with shutter shades" },
  { src: "/hero/crown.jpg", alt: "Blue-lit crown on a dark field" },
  { src: "/hero/cyber-fox.jpg", alt: "Cyber fox portrait in a rain-soaked city" },
];

const flowSteps = [
  { lines: ["Create the project"], ink: "#1578d6", glow: "#3aa0ff", x: 100, y: 132 },
  { lines: ["Upload or draw", "the layers"], ink: "#e07a00", glow: "#ff9a1f", x: 300, y: 228 },
  { lines: ["Set weights", "and rules"], ink: "#7c3aed", glow: "#a78bfa", x: 500, y: 132 },
  { lines: ["Plan, then render"], ink: "#0e8f86", glow: "#2ee0cf", x: 700, y: 228 },
  { lines: ["Validate and export"], ink: "#6d28d9", glow: "#c084fc", x: 900, y: 132 },
];

function ProcessFlow() {
  return (
    <div className="mb-16">
      <ol className="sr-only">
        {flowSteps.map((step) => (
          <li key={step.lines.join(" ")}>{step.lines.join(" ")}</li>
        ))}
      </ol>
      <ol aria-hidden className="mx-auto flex max-w-md flex-col md:hidden">
        {flowSteps.map((step, index) => (
          <li key={step.lines.join(" ")} className="flex gap-4">
            <div className="flex flex-col items-center">
              <span className="flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-full bg-white">
                <span className="text-sm font-bold leading-none" style={{ color: step.ink }}>
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="mt-1 text-[9px] font-bold tracking-[0.14em]" style={{ color: step.ink }}>
                  STEP
                </span>
              </span>
              {index < flowSteps.length - 1 ? (
                <span
                  className="my-2 w-2 flex-1 rounded-full"
                  style={{ background: `linear-gradient(${step.glow}, ${flowSteps[index + 1].glow})`, minHeight: "1.5rem" }}
                />
              ) : null}
            </div>
            <p className="pt-4 text-sm font-semibold" style={{ color: step.glow }}>
              {step.lines.join(" ")}
            </p>
          </li>
        ))}
      </ol>
      <div className="mx-auto hidden aspect-[1000/360] md:block">
        <svg viewBox="0 0 1000 360" className="h-full w-full font-sans" aria-hidden>
          <defs>
            <linearGradient id="workflow-path" x1="100" y1="0" x2="900" y2="0" gradientUnits="userSpaceOnUse">
              {flowSteps.map((step, index) => (
                <stop key={step.glow} offset={`${index / (flowSteps.length - 1)}`} stopColor={step.glow} />
              ))}
            </linearGradient>
          </defs>
          <path
            d="M 100 132 C 175 132, 225 228, 300 228 C 375 228, 425 132, 500 132 C 575 132, 625 228, 700 228 C 775 228, 825 132, 900 132"
            fill="none"
            stroke="url(#workflow-path)"
            strokeWidth="78"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {flowSteps.map((step, index) => {
            const above = index % 2 === 0;
            const labelYs = above ? (step.lines.length === 1 ? [78] : [60, 80]) : step.lines.length === 1 ? [312] : [294, 314];
            const number = String(index + 1).padStart(2, "0");
            return (
              <g key={step.lines.join(" ")}>
                <text fill={step.glow} fontSize="15" fontWeight="600" textAnchor="middle">
                  {step.lines.map((line, lineIndex) => (
                    <tspan key={line} x={step.x} y={labelYs[lineIndex]}>
                      {line}
                    </tspan>
                  ))}
                </text>
                <circle cx={step.x} cy={step.y} r="36" fill="#ffffff" />
                <text x={step.x} y={step.y - 2} fill={step.ink} fontSize="20" fontWeight="700" textAnchor="middle">
                  {number}
                </text>
                <text x={step.x} y={step.y + 14} fill={step.ink} fontSize="8" fontWeight="700" letterSpacing="1.4" textAnchor="middle">
                  STEP
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

const modules: [string, string, LucideIcon][] = [
  ["Editor", "Crop, color, layers, undo, and transparent PNG export.", Crop],
  ["Traits", "Layer order, weights, exact counts, and compatibility rules.", Layers],
  ["Generator", "Seeded unique combinations, with invalid pairs refused up front.", Dices],
  ["Automation", "Save a recipe and run it across a folder, with a dry run first.", Workflow],
  ["Metadata", "ERC-721 and Metaplex JSON, plus a spreadsheet of the same tokens.", FileJson],
  ["Publishing", "Validation report, ZIP, and optional Pinata pinning.", PackageCheck],
];

export default function HomePage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <p className="w-full text-sm tracking-[0.2em] text-purple sm:w-auto">NFT CREATIVE STUDIO</p>
        <div className="ml-auto flex shrink-0 gap-2">
          <Link href="/login" className="whitespace-nowrap rounded-full px-4 py-2 text-sm text-mute hover:text-paper">
            Sign in
          </Link>
          <Link href="/register" className="whitespace-nowrap rounded-full bg-purple px-4 py-2 text-sm font-medium text-ink">
            Open the studio
          </Link>
        </div>
      </header>
      <section className="grid items-center gap-10 py-16 lg:grid-cols-2 lg:gap-12">
        <div>
          <h1 className="font-serif text-5xl leading-[1.05] md:text-7xl">From raw frames to a mint-ready collection.</h1>
          <p className="mt-6 max-w-xl text-lg text-mute">
            One workspace for the edit, the trait stack, the rarity rules, the metadata, and the export. Invalid combinations are blocked while the collection is planned, not after you have rendered a thousand files.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/register" className="rounded-full bg-purple px-5 py-3 text-sm font-medium text-ink">
              Start a project
            </Link>
            <Link href="/login" className="rounded-full border border-white/15 px-5 py-3 text-sm">
              Use the demo project
            </Link>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {heroes.map((hero) => (
            <div key={hero.src} className="relative aspect-square overflow-hidden rounded-3xl border border-white/10">
              <Image src={hero.src} alt={hero.alt} fill className="object-cover" sizes="(min-width: 1024px) 280px, 45vw" />
            </div>
          ))}
        </div>
      </section>
      <ProcessFlow />
      <section className="grid gap-4 md:grid-cols-3">
        {modules.map(([title, copy, Icon]) => (
          <article key={title} className="rounded-3xl border border-white/10 bg-black/20 p-5">
            <h2 className="flex items-center gap-2.5 font-serif text-2xl">
              <Icon size={22} strokeWidth={1.75} className="shrink-0 text-purple" aria-hidden />
              {title}
            </h2>
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
