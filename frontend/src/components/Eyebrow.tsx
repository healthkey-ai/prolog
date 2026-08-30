import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The small uppercase label above a heading (question number, section, page kind). */
export function Eyebrow({ children, onPrimary, className, as: Tag = "p" }: { children: ReactNode; onPrimary?: boolean; className?: string; as?: "p" | "h3" }) {
  return <Tag className={cn("text-[13px] font-medium uppercase tracking-[0.08em]", onPrimary ? "text-on-primary/80" : "text-ink-soft", className)}>{children}</Tag>;
}
