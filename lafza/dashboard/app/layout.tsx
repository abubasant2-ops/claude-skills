import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import "./globals.css";

// Bundled locally — no network font fetching (offline-friendly, blueprint §9).
const plexArabic = localFont({
  src: [
    { path: "./fonts/IBMPlexSansArabic-Regular.ttf", weight: "400" },
    { path: "./fonts/IBMPlexSansArabic-Bold.ttf", weight: "700" },
  ],
  variable: "--font-plex-arabic",
});

export const metadata: Metadata = {
  title: "لفظة — لوحة الأخصائي",
  description: "لوحة أخصائي التخاطب: الحالات، الخطط، وتقدم الأطفال",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // RTL first (CLAUDE.md rule 1).
    <html lang="ar" dir="rtl" className={`${plexArabic.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-[#FAF8F4] font-[family-name:var(--font-plex-arabic)] text-[#1B2A4A]">
        <header className="bg-[#1B2A4A] text-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-xl font-bold">
              لفظة{" "}
              <span className="font-normal text-[#F2A93B]">
                · لوحة الأخصائي
              </span>
            </Link>
            <span className="text-sm text-white/70">نسخة تجريبية — MVP</span>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
