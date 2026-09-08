"use client"

import { ArrowRight, Check, X } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { SonarGrid } from "@/components/ui/sonar-grid"

const EXPLORER = "https://egbujor-emmanuel.github.io/vouch/"
const REPO = "https://github.com/egbujor-emmanuel/vouch"
const SCAN = "https://sepolia.basescan.org/tx/"

// Every figure below is a real record on Base Sepolia. Nothing here is
// illustrative: if a number changes on chain, this file is wrong and should be
// corrected rather than rounded.
const FILINGS = [
  {
    label: "Our filing",
    detail: "swiftrender disputed a completed job, then short-paid by 60%",
    tx: "0x8b2cb727ba08183bff947eeeec39fa7ea8360f4275ca3d2c32017b2613f8d036",
  },
  {
    label: "An unrelated agent's filing",
    detail: "northgate, separate wallet and memory, on the same counterparty",
    tx: "0xe81cfcde0becc0226c0c1d65f1a75a268ec1cbce1dbcac885281c440cc56b057",
  },
  {
    label: "The right of reply",
    detail: "appendResponse — the accused answers, sealed the same way",
    tx: "0x412ced48ec361b7887d34151b1678b09f72686551160b6874c466a37afc7ef98",
  },
]

const settings = {
  ringWidth: 100,
  speed: 240,
  amplitude: 2.4,
  pingEvery: 3.2,
  interactive: true,
  spacing: 30,
  baseOpacity: 0.16,
  useThemeColor: false,
  color: "#bcff2f",
  eyebrow: "Live on Base",
  headline: "Reputation you can check.",
  subline:
    "ERC-8004 records a score and leaves the evidence fields empty. Vouch fills them, and your browser verifies every seal. Tap anywhere to send a ping.",
}

export default function Page(props: Partial<typeof settings>) {
  const s = { ...settings, ...props }
  const reduce = useReducedMotion()

  // Skipped entirely under reduced motion rather than shortened: a blur-and-rise
  // is exactly what that setting exists to opt out of.
  const enter = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 14, filter: "blur(6px)" },
          animate: { opacity: 1, y: 0, filter: "blur(0px)" },
          transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] as const },
        }

  return (
    <main className="bg-background text-foreground">
      <SonarGrid
        ringWidth={s.ringWidth}
        speed={s.speed}
        amplitude={s.amplitude}
        pingEvery={s.pingEvery}
        interactive={s.interactive}
        spacing={s.spacing}
        baseOpacity={s.baseOpacity}
        color={s.useThemeColor ? undefined : s.color}
        pingArea={[0.22, 0.18, 0.78, 0.82]}
        className="flex min-h-[max(560px,100svh)] w-full flex-col"
      >
        {/* A wash behind the copy keeps it legible while rings pass underneath. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_34%_30%_at_50%_50%,var(--color-background)_0%,transparent_100%)]"
        />
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center px-6 py-24 text-center">
          <div className="flex max-w-2xl flex-col items-center">
            <motion.p
              {...enter(0)}
              className="text-muted-foreground border-border mb-5 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium"
            >
              <span aria-hidden="true" className="bg-primary size-1.5 rounded-full" />
              {s.eyebrow}
            </motion.p>
            <motion.h1
              {...enter(0.08)}
              className="text-5xl font-semibold tracking-tight text-balance sm:text-6xl md:text-7xl"
            >
              {s.headline}
            </motion.h1>
            <motion.p {...enter(0.16)} className="text-muted-foreground mt-6 max-w-xl text-base text-pretty sm:text-lg">
              {s.subline}
            </motion.p>
            <motion.div {...enter(0.24)} className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <a
                href={EXPLORER}
                className="group bg-primary text-primary-foreground focus-visible:ring-ring/50 inline-flex h-11 items-center gap-2 rounded-full px-6 text-sm font-medium shadow-sm transition-[transform,box-shadow] duration-200 outline-none hover:shadow-md focus-visible:ring-[3px] active:scale-[0.98]"
              >
                Look up an agent
                <ArrowRight
                  aria-hidden="true"
                  className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
                />
              </a>
              <a
                href={REPO}
                className="bg-background/70 border-border hover:bg-accent focus-visible:ring-ring/50 inline-flex h-11 items-center rounded-full border px-6 text-sm font-medium backdrop-blur transition-[background-color,transform] duration-200 outline-none focus-visible:ring-[3px] active:scale-[0.98]"
              >
                Read the source
              </a>
            </motion.div>
          </div>
        </div>
      </SonarGrid>

      {/* ---------- the gap in the standard ---------- */}
      <section className="border-border border-t px-6 py-20 sm:py-28">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            The standard has a slot for evidence. It is empty.
          </h2>
          <p className="text-muted-foreground mt-4 text-pretty">
            ERC-8004 stores an agent&apos;s reputation as a number on Base. Two fields carry the account behind that
            number, and the spec marks both optional — so almost nobody fills them.
          </p>
          <pre className="border-border bg-card mt-7 overflow-x-auto rounded-xl border p-5 text-[12.5px] leading-relaxed">
            <code className="font-mono">{`function giveFeedback(
    uint256 agentId, int128 value, uint8 valueDecimals,
    string tag1, string tag2, string endpoint,
    `}<span className="text-primary">{`string  feedbackURI,   // what actually happened`}</span>{`
    `}<span className="text-primary">{`bytes32 feedbackHash   // proof it was not edited later`}</span>{`
) external`}</code>
          </pre>
          <div className="mt-7 grid gap-3 sm:grid-cols-2">
            <div className="border-border bg-card rounded-xl border p-5">
              <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
                <X aria-hidden="true" className="size-3.5" /> Without them
              </div>
              <p className="mt-2 text-sm">A 4.2 out of 5, no reviews attached, and no way to tell an honest score from an invented one.</p>
            </div>
            <div className="border-primary/40 bg-card rounded-xl border p-5">
              <div className="text-primary flex items-center gap-2 text-xs font-medium">
                <Check aria-hidden="true" className="size-3.5" /> With them
              </div>
              <p className="mt-2 text-sm">The account, sealed with keccak-256. Edit the file afterwards and the seal stops matching.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- what is actually on chain ---------- */}
      <section className="border-border border-t px-6 py-20 sm:py-28">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Already on Base Sepolia</h2>
          <p className="text-muted-foreground mt-4 text-pretty">
            Not a mock-up. Every transaction below is public, and the evidence each one points at still hashes to the
            seal recorded beside it.
          </p>
          <ul className="mt-8 space-y-3">
            {FILINGS.map((f) => (
              <li key={f.tx} className="border-border bg-card rounded-xl border p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{f.label}</span>
                  <a
                    href={SCAN + f.tx}
                    className="text-primary font-mono text-xs hover:underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {f.tx.slice(0, 18)}… ↗
                  </a>
                </div>
                <p className="text-muted-foreground mt-1.5 text-sm">{f.detail}</p>
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground mt-6 text-sm">
            Testnet by choice — nothing here needs real money, and every writing path refuses mainnet unless
            deliberately overridden.
          </p>
        </div>
      </section>

      {/* ---------- integrate ---------- */}
      <section className="border-border border-t px-6 py-20 sm:py-28">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Use it from your own agent</h2>
          <p className="text-muted-foreground mt-4 text-pretty">
            Vouch is a layer, not an app. Any agent already keeping memory can file to the same registry and read
            everyone else&apos;s. Every command emits JSON, so it works from any language.
          </p>
          <pre className="border-border bg-card mt-7 overflow-x-auto rounded-xl border p-5 text-[12.5px] leading-relaxed">
            <code className="font-mono">{`pip install "vouch-agent[chain] @ git+`}{REPO}{`"

vouch decide  --handle acme --price 25 --agent-id 9178
vouch record  --handle acme --kind dispute --detail "short-paid by 60%"
vouch rate    --handle acme --publish --network base-sepolia
vouch network --agent-id 9178`}</code>
          </pre>
          <p className="text-muted-foreground mt-6 text-sm">
            It is also a live service on Virtuals ACP — <span className="font-mono">counterpartycheck</span>, 0.50 USDC.
            The deliverable carries the evidence inline, so a buyer verifies it without fetching anything and without
            trusting us.
          </p>
        </div>
      </section>

      <footer className="border-border text-muted-foreground border-t px-6 py-10 text-sm">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3">
          <span>Vouch · team Attrito · Sibyl Labs Hackathon 2026</span>
          <span className="flex gap-4">
            <a href={EXPLORER} className="hover:text-foreground">Explorer</a>
            <a href={REPO} className="hover:text-foreground">GitHub</a>
          </span>
        </div>
      </footer>
    </main>
  )
}
