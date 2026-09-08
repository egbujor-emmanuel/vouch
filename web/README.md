# Vouch — web

The marketing front door. The product itself lives one directory up, and the
explorer that verifies filings in the browser is in [`../docs`](../docs).

Kept as a separate app on purpose: `docs/` is a zero-dependency page that loads
three local files and nothing else, and it is what ships. Nothing here can break it.

```bash
npm install
npm run dev     # http://localhost:3000
npm run build
```

Next 16 (App Router) · React 19 · TypeScript · Tailwind v4 · shadcn (base-nova).

Tailwind v4 is CSS-first, so there is no `tailwind.config.ts`; the theme tokens
live in `app/globals.css`.

`components/ui/sonar-grid.tsx` is a canvas dot-field that answers taps with
expanding rings. It reads the resolved `text-primary` colour so it follows the
theme, idles when no ring is alive, pauses off-screen and in hidden tabs, and
renders a still grid under `prefers-reduced-motion`.
