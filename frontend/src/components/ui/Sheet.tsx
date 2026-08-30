import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface SheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  closeLabel: string;
}

/** Bottom sheet (mobile) / side panel (≥1024px) built on the native <dialog>. */
export function Sheet({ open, onClose, title, children, closeLabel }: SheetProps) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-labelledby="sheet-title"
      className={cn(
        "m-0 h-auto max-h-[85vh] w-full max-w-none rounded-t-[var(--p-radius-sheet)] border-0 bg-surface p-0 text-ink shadow-[var(--p-shadow)]",
        "backdrop:bg-ink/40 open:flex open:flex-col",
        "fixed inset-x-0 bottom-0 top-auto",
        "lg:inset-y-0 lg:left-auto lg:right-0 lg:h-full lg:max-h-none lg:w-[420px] lg:rounded-none lg:rounded-l-[var(--p-radius-sheet)]",
      )}
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 id="sheet-title" className="text-lg">
          {title}
        </h2>
        <button type="button" onClick={onClose} className="min-h-[44px] rounded-[var(--p-radius-button)] px-3 text-primary hover:bg-tint">
          {closeLabel}
        </button>
      </div>
      <div className="overflow-y-auto px-5 py-3">{children}</div>
    </dialog>
  );
}
