import { useThemeDecor } from "@/theme/useTheme";

// Copy is left-aligned, so shapes hug the right edge and the corners — never behind text.
const POSITIONS = ["-right-16 -top-16 w-72 rotate-12", "-right-28 -bottom-28 w-80 -rotate-6", "-right-12 top-1/2 w-32"];

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
