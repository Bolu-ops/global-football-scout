import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Global Football Scout",
  description: "Data-driven player similarity and transfer intelligence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body className="min-h-screen">
        <header className="border-b border-border bg-surface/60 backdrop-blur">
          <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-sm font-semibold tracking-[0.18em] uppercase">Global Football Scout</span>
              <span className="text-xs text-muted">find your next player</span>
            </Link>
            <div className="flex gap-6 text-sm text-ink-2">
              <Link href="/" className="hover:text-ink">Scout</Link>
              <Link href="/model" className="hover:text-ink">Methodology</Link>
              <Link href="/sources" className="hover:text-ink">Data sources</Link>
              <Link href="/admin" className="hover:text-ink">Admin</Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-7xl px-6 py-8 text-xs text-muted">
          Event data: StatsBomb Open Data (statsbomb.com) — non-commercial research use, attribution required.
          Association coefficients: UEFA. Rankings are produced by statistical models; nothing is fabricated —
          unavailable values are shown as “Data unavailable”.
        </footer>
      </body>
    </html>
  );
}
