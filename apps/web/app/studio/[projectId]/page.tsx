"use client";

import dynamic from "next/dynamic";

const Workspace = dynamic(() => import("@/components/studio/workspace").then((mod) => mod.Workspace), { ssr: false });

export default function ProjectPage() {
  return <Workspace />;
}
