"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearAuth, getUser, type User } from "@/lib/api";

export default function Shell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const u = getUser();
    if (!u) router.replace("/login");
    else setUser(u);
  }, [router]);

  if (!user) return null;

  const logout = () => {
    clearAuth();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-brand-500 text-white shadow">
        <div className="container mx-auto px-4 py-3 flex items-center gap-4">
          <Link href="/dashboard" className="text-xl font-bold tracking-tight">
            ArcVision AI
          </Link>
          <nav className="flex gap-3 text-sm opacity-90">
            <NavLink href="/dashboard" pathname={pathname}>لوحة القيادة</NavLink>
            <NavLink href="/projects/new" pathname={pathname}>مشروع جديد</NavLink>
            <NavLink href="/price-book" pathname={pathname}>دفتر الأسعار</NavLink>
          </nav>
          <div className="ms-auto flex items-center gap-3 text-sm">
            <span className="opacity-90">
              {user.full_name || user.email}
              <span className="opacity-60"> · {user.role}</span>
            </span>
            <button onClick={logout} className="bg-brand-700 hover:bg-brand-600 px-3 py-1 rounded">
              خروج
            </button>
          </div>
        </div>
      </header>
      <main className="container mx-auto px-4 py-6 flex-1">{children}</main>
      <footer className="text-center text-xs text-gray-400 py-4">
        ArcVision AI — MVP · الحوكمة قبل الجمال
      </footer>
    </div>
  );
}

function NavLink({ href, pathname, children }: { href: string; pathname: string | null; children: React.ReactNode }) {
  const active = pathname?.startsWith(href);
  return (
    <Link
      href={href}
      className={`px-2 py-1 rounded ${active ? "bg-brand-700" : "hover:bg-brand-600"}`}
    >
      {children}
    </Link>
  );
}
