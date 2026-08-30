/** Theme document as served by GET /api/run/themes/{code}/ (asset paths already absolute). */
export interface Palette {
  primary: string;
  primary_deep?: string;
  on_primary?: string;
  secondary: string;
  accent: string;
  focus?: string;
  ground: string;
  surface: string;
  tint: string;
  ink: string;
  ink_soft: string;
  line: string;
  error: string;
  success: string;
}

export interface FontFace {
  family: string;
  src: string;
  weight?: string;
  style?: "normal" | "italic";
  display?: "swap" | "block" | "fallback" | "optional";
}

export interface Theme {
  code: string;
  name: string;
  version?: string;
  color_scheme?: "light" | "light-dark";
  colors: { light: Palette; dark?: Partial<Palette> };
  typography?: {
    heading_family?: string;
    body_family?: string;
    heading_weight?: number;
    body_weight?: number;
    tracking?: string;
    base_size_px?: number;
    font_faces?: FontFace[];
    google_fonts?: string[];
  };
  shape?: { radius_card?: string; radius_input?: string; radius_button?: string; radius_sheet?: string; shadow?: string };
  layout?: { copy_alignment?: "left" | "center"; content_max_width?: string; immersive_intro?: boolean; logo_placement?: "top-left" | "top-right" };
  assets?: { logo?: string; logo_on_primary?: string; favicon?: string; decor?: string[] };
  motion?: { enabled?: boolean };
  strings?: Record<string, Record<string, string>>;
  warnings?: string[];
}
