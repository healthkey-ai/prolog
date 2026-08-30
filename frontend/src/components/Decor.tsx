import { useThemeDecor } from "@/theme/useTheme";

const POSITIONS = ["-right-16 -top-16 w-72 rotate-12", "-left-20 bottom-8 w-80 -rotate-6", "right-8 bottom-24 w-40"];

/** Decorative theme shapes on immersive screens (aria-hidden, never behind copy). */
export function Decor() {
  const decor = useThemeDecor();
  if (!decor.length) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden data-testid="decor">
      {decor.slice(0, 3).map((src, i) => (
        <img key={src} src={src} alt="" className={`absolute opacity-80 ${POSITIONS[i]}`} />
      ))}
    </div>
  );
}
