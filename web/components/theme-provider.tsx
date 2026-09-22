"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * FlakeProof is dark-only (docs/07-UI-SPEC.md: "Theme: dark by default" —
 * only dark tokens are specced, no light palette exists). `forcedTheme`
 * locks it regardless of system preference; next-themes is still used
 * (rather than a bare `className="dark"`) because `components/ui/sonner.tsx`
 * reads the theme via `useTheme()`.
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider attribute="class" forcedTheme="dark" enableSystem={false} {...props}>
      {children}
    </NextThemesProvider>
  );
}
