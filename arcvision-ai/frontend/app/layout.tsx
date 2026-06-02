import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ArcVision AI",
  description: "منصة ذكاء اصطناعي لتحليل المشاريع الإنشائية",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body className="min-h-screen font-sans">{children}</body>
    </html>
  );
}
