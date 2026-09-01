"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import Shell from "@/components/Shell";
import { API_URL, apiFetch, getUser } from "@/lib/api";
import { SAR } from "@/lib/format";

interface CostSummary {
  direct: string;
  indirect: string;
  contingency: string;
  total: string;
  bid_price: string;
  margin_amount: string;
  cost_per_m2?: string | null;
  by_category: Record<string, string>;
  line_count: number;
  priced_count: number;
  unpriced_categories: string[];
}

const fetcher = (p: string) => apiFetch<CostSummary>(p);

export default function CostPage({ params }: { params: { id: string } }) {
  const { data, mutate } = useSWR(`/v1/projects/${params.id}/cost`, fetcher);
  const [indirect, setIndirect] = useState("0.08");
  const [contingency, setContingency] = useState("0.05");
  const [margin, setMargin] = useState("0.14");
  const user = typeof window !== "undefined" ? getUser() : null;
  const canSeeMargin = user && user.role !== "client";

  const recalc = async () => {
    await apiFetch(`/v1/projects/${params.id}/cost/recalculate`, {
      method: "POST",
      body: JSON.stringify({
        indirect_pct: Number(indirect),
        contingency_pct: Number(contingency),
        margin_pct: Number(margin),
      }),
    });
    mutate();
  };

  if (!data) return <Shell><p>جارٍ التحميل...</p></Shell>;

  const total = Number(data.total);
  const byCat = Object.entries(data.by_category).sort((a, b) => Number(b[1]) - Number(a[1]));
  const max = byCat.length ? Number(byCat[0][1]) : 1;

  return (
    <Shell>
      <div className="flex items-center gap-3 mb-1">
        <Link href={`/projects/${params.id}`} className="text-sm text-brand-500 hover:underline">← المشروع</Link>
      </div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">التكلفة والملخص المالي</h1>
        <a href={`${API_URL}/v1/projects/${params.id}/reports/boq.xlsx`}
           className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-lg text-sm"
           target="_blank" rel="noopener">
          تصدير BOQ (xlsx)
        </a>
      </div>

      <div className="grid md:grid-cols-3 gap-4 mb-6">
        <Card title="التكلفة المباشرة" value={SAR.format(Number(data.direct))} />
        <Card title="غير المباشرة" value={SAR.format(Number(data.indirect))} />
        <Card title="الطوارئ" value={SAR.format(Number(data.contingency))} />
        <Card title="الإجمالي" value={SAR.format(total)} highlight />
        {canSeeMargin && <Card title="سعر العرض (Bid)" value={SAR.format(Number(data.bid_price))} highlight />}
        <Card title="تكلفة م²" value={data.cost_per_m2 ? SAR.format(Number(data.cost_per_m2)) : "—"} />
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
        <h2 className="font-bold mb-4">التوزيع حسب الفئة</h2>
        {byCat.length === 0 && (
          <p className="text-sm text-gray-400">
            لا توجد بنود مُسعّرة بعد. اعتمد بنود الحصر أولاً.
          </p>
        )}
        {byCat.map(([cat, val]) => {
          const v = Number(val);
          const pct = total ? (v / total) * 100 : 0;
          return (
            <div key={cat} className="mb-2">
              <div className="flex justify-between text-sm">
                <span>{cat}</span>
                <span className="font-mono">{SAR.format(v)} · {pct.toFixed(1)}%</span>
              </div>
              <div className="bg-gray-100 h-2 rounded">
                <div className="bg-brand-500 h-2 rounded" style={{ width: `${(v / max) * 100}%` }}></div>
              </div>
            </div>
          );
        })}
        {data.unpriced_categories.length > 0 && (
          <div className="mt-4 bg-amber-50 text-amber-800 text-xs rounded p-3">
            ⚠ فئات بدون سعر في دفتر الأسعار:{" "}
            <strong>{data.unpriced_categories.join(", ")}</strong>.
            أضف أسعارها في <Link href="/price-book" className="underline">دفتر الأسعار</Link> ثم أعد الحساب.
          </div>
        )}
      </div>

      {canSeeMargin && (
        <div className="bg-white rounded-xl shadow-sm p-6">
          <h2 className="font-bold mb-4">سيناريو التسعير</h2>
          <div className="grid md:grid-cols-3 gap-4 mb-4">
            <Pct label="غير مباشرة %" value={indirect} setValue={setIndirect} />
            <Pct label="طوارئ %" value={contingency} setValue={setContingency} />
            <Pct label="هامش الربح %" value={margin} setValue={setMargin} />
          </div>
          <button onClick={recalc}
                  className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-lg text-sm">
            إعادة الحساب
          </button>
        </div>
      )}
    </Shell>
  );
}

function Card({ title, value, highlight }: { title: string; value: string; highlight?: boolean }) {
  return (
    <div className={`rounded-xl p-4 shadow-sm ${highlight ? "bg-brand-500 text-white" : "bg-white"}`}>
      <div className={`text-xs mb-1 ${highlight ? "text-brand-100" : "text-gray-500"}`}>{title}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function Pct({ label, value, setValue }: { label: string; value: string; setValue: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-xs text-gray-500 mb-1 inline-block">{label}</span>
      <input type="number" step="0.01" min="0" max="1"
             className="w-full border rounded-lg px-3 py-2"
             value={value} onChange={(e) => setValue(e.target.value)} />
    </label>
  );
}
