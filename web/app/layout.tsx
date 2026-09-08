import type { Metadata, Viewport } from "next"
import { Geist, Geist_Mono } from "next/font/google"
import "./globals.css"

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
})

const title = "Vouch — reputation you can check"
const description =
  "ERC-8004 records a reputation score on Base and leaves the evidence fields empty. Vouch fills them with hash-committed agent memory, and your browser verifies every seal."
const url = "https://egbujor-emmanuel.github.io/vouch/"

export const metadata: Metadata = {
  title,
  description,
  metadataBase: new URL(url),
  applicationName: "Vouch",
  authors: [{ name: "Attrito" }],
  keywords: ["ERC-8004", "Base", "AI agents", "agent reputation", "Sibyl Memory", "Virtuals ACP"],
  openGraph: { title, description, url, siteName: "Vouch", type: "website" },
  twitter: { card: "summary_large_image", title, description },
}

// The page is a black canvas field; telling the browser so stops a white flash
// on load and keeps native UI (scrollbars, form controls) in the right theme.
export const viewport: Viewport = {
  themeColor: "#000000",
  colorScheme: "dark",
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="dark">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>{children}</body>
    </html>
  )
}
