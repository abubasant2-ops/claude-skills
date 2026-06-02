"use client";

import { useState } from "react";
import useSWR from "swr";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { SAR } from "@/lib/format";

interface PB {
  id: string;
  category: string;
  description?: string | null;
  unit: string;
  material_rate: string;
  labor_rate: string;
  equipment_rate: string;
  waste_factor: string;
  source: string;
}

const fetcher = (p: string) => apiFetch<PB[]>(p);

const EMPTY = {
  category: "concrete",
  description: "",
  unit: "m3",
  material_rate: "0",
  labor_rate: "0",
  equipment_rate: "0",
  waste_factor: "0.05",
};

export default function PriceBookPage() {
  const { data, mutate } = useSWR("/v1/org/price-book", fetcher);
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await apiFetch("/v1/org/price-book", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          material_rate: Number(form.material_rate),
          labor_rate: Number(form.labor_rate),
          equipment_rate: Number(form.equipment_rate),
          waste_factor: Number(form.waste_factor),
        }),
      });
      setForm({ ...EMPTY });
      mutate();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell>
      <h1 className="text-2xl font-bold mb-6">دفتر الأسعار</h1>
      <p className="text-sm text-gray-500 mb-4">
        الذاكرة السعرية المؤسسية. يُفضّل تحديث الأسعار من العقود السابقة لمنظور القوس
        (هرم الثقة السعري — PRD §11.2).
      </p>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead className="bg-brand-50 text-brand-700">
            <tr>
              <th className="text-start p-3">الفئة</th>
              <th className="text-start p-3">الوصف</th>
              <th className="text-start p-3">الوحدة</th>
              <th className="text-start p-3">مادة</th>
              <th className="text-start p-3">عمالة</th>
              <th className="text-start p-3">معدات</th>
              <th className="text-start p-3">هدر</th>
              <th className="text-start p-3">المصدر</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((p) => (
              <tr key={p.id} className="border-t">
                <td className="p-3 font-medium">{p.category}</td>
                <td className="p-3 text-gray-600">{p.description || "—"}</td>
                <td className="p-3">{p.unit}</td>
                <td className="p-3 font-mono">{SAR.format(Number(p.material_rate))}</td>
                <td className="p-3 font-mono">{SAR.format(Number(p.labor_rate))}</td>
                <td className="p-3 font-mono">{SAR.format(Number(p.equipment_rate))}</td>
                <td className="p-3">{(Number(p.waste_factor) * 100).toFixed(1)}%</td>
                <td className="p-3 text-xs">{p.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <form onSubmit={save} className="bg-white rounded-xl shadow-sm p-6 grid md:grid-cols-4 gap-3">
        <Input label="الفئة" value={form.category} onChange={(v) => setForm({ ...form, category: v })} />
        <Input label="الوصف" value={form.description} onChange={(v) => setForm({ ...form, description: v })} />
        <Input label="الوحدة" value={form.unit} onChange={(v) => setForm({ ...form, unit: v })} />
        <Input label="هدر %" value={form.waste_factor} onChange={(v) => setForm({ ...form, waste_factor: v })} type="number" />
        <Input label="سعر المادة" value={form.material_rate} onChange={(v) => setForm({ ...form, material_rate: v })} type="number" />
        <Input label="سعر العمالة" value={form.labor_rate} onChange={(v) => setForm({ ...form, labor_rate: v })} type="number" />
        <Input label="سعر المعدات" value={form.equipment_rate} onChange={(v) => setForm({ ...form, equipment_rate: v })} type="number" />
        <button disabled={busy}
                className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white rounded-lg self-end px-4 py-2">
          {busy ? "..." : "إضافة"}
        </button>
      </form>
    </Shell>
  );
}

function Input({ label, value, onChange, type = "text" }:
  { label: string; value: string; onChange: (v: string) => void; type?: string }) {
  return (
    <label className="block">
      <span className="text-xs text-gray-500 mb-1 inline-block">{label}</span>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
             step={type === "number" ? "any" : undefined}
             className="w-full border rounded-lg px-3 py-2" />
    </label>
  );
}
