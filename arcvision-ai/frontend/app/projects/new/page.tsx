"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    name: "",
    client_name: "",
    project_type: "residential",
    location_city: "الرياض",
    gross_area_m2: "" as string,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const project = await apiFetch<{ id: string }>("/v1/projects", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          gross_area_m2: form.gross_area_m2 ? Number(form.gross_area_m2) : null,
        }),
      });
      router.push(`/projects/${project.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <h1 className="text-2xl font-bold mb-6">مشروع جديد</h1>
      <form onSubmit={submit} className="bg-white rounded-xl shadow-sm p-6 max-w-2xl space-y-4">
        <Field label="اسم المشروع" required>
          <input className="w-full border rounded-lg px-3 py-2"
                 value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="العميل">
          <input className="w-full border rounded-lg px-3 py-2"
                 value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} />
        </Field>
        <Field label="نوع المشروع">
          <select className="w-full border rounded-lg px-3 py-2"
                  value={form.project_type} onChange={(e) => setForm({ ...form, project_type: e.target.value })}>
            <option value="residential">سكني</option>
            <option value="commercial">تجاري</option>
            <option value="infrastructure">بنية تحتية</option>
            <option value="industrial">صناعي</option>
          </select>
        </Field>
        <Field label="المدينة">
          <input className="w-full border rounded-lg px-3 py-2"
                 value={form.location_city} onChange={(e) => setForm({ ...form, location_city: e.target.value })} />
        </Field>
        <Field label="المساحة الإجمالية (م²)">
          <input type="number" min="0" step="0.01" className="w-full border rounded-lg px-3 py-2"
                 value={form.gross_area_m2}
                 onChange={(e) => setForm({ ...form, gross_area_m2: e.target.value })} />
        </Field>

        {error && <div className="bg-red-50 text-red-700 text-sm rounded p-2">{error}</div>}

        <button disabled={busy}
                className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white px-5 py-2 rounded-lg">
          {busy ? "..." : "إنشاء المشروع"}
        </button>
      </form>
    </Shell>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm text-gray-700 mb-1 inline-block">
        {label}{required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}
