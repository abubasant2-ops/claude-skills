"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("owner@arcoview.sa");
  const [password, setPassword] = useState("ChangeMe!123");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-bl from-brand-50 to-white">
      <form onSubmit={submit} className="bg-white p-8 rounded-xl shadow-md w-full max-w-md">
        <h1 className="text-2xl font-bold text-brand-700 mb-1">ArcVision AI</h1>
        <p className="text-sm text-gray-500 mb-6">
          منصة تحليل المشاريع الإنشائية — تسجيل الدخول
        </p>

        <label className="block text-sm mb-1">البريد الإلكتروني</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 mb-4"
          required
        />

        <label className="block text-sm mb-1">كلمة المرور</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border rounded-lg px-3 py-2 mb-4"
          required
        />

        {error && (
          <div className="bg-red-50 text-red-700 text-sm rounded p-2 mb-3">{error}</div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white py-2 rounded-lg font-medium"
        >
          {busy ? "..." : "دخول"}
        </button>

        <p className="text-xs text-gray-400 mt-4 text-center">
          حسابات تجريبية: owner / estimator / qs / pm / exec / client @arcoview.sa
        </p>
      </form>
    </div>
  );
}
