"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { NUM3, confidenceClass, statusLabel } from "@/lib/format";

interface TakeoffItem {
  id: string;
  category: string;
  description?: string | null;
  unit: string;
  quantity: string;
  original_quantity?: string | null;
  confidence: string;
  review_status: string;
  source_element_ids?: string[] | null;
}

interface Summary {
  items: TakeoffItem[];
  total_items: number;
  low_confidence: number;
  approved: number;
}

const fetcher = (p: string) => apiFetch<Summary>(p);

export default function TakeoffPage({ params }: { params: { id: string } }) {
  const { data, mutate } = useSWR(`/v1/projects/${params.id}/takeoff`, fetcher);
  const [editing, setEditing] = useState<string | null>(null);
  const [editQty, setEditQty] = useState<string>("");

  const patch = async (itemId: string, body: Record<string, unknown>) => {
    await apiFetch(`/v1/takeoff/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    mutate();
  };

  const approveAll = async () => {
    await apiFetch(`/v1/projects/${params.id}/takeoff/approve`, { method: "POST" });
    mutate();
  };

  return (
    <Shell>
      <div className="flex items-center gap-3 mb-1">
        <Link href={`/projects/${params.id}`} className="text-sm text-brand-500 hover:underline">← المشروع</Link>
      </div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">مراجعة الحصر</h1>
        <div className="flex gap-2">
          <button onClick={approveAll}
                  className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-lg text-sm">
            اعتماد الكل ✓
          </button>
          <Link href={`/projects/${params.id}/cost`}
                className="bg-white border border-brand-500 text-brand-500 hover:bg-brand-50 px-4 py-2 rounded-lg text-sm">
            متابعة إلى التكلفة ←
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Kpi label="إجمالي البنود" value={data?.total_items ?? "—"} />
        <Kpi label="منخفضة الثقة" value={data?.low_confidence ?? "—"} tone="warn" />
        <Kpi label="معتمدة" value={data?.approved ?? "—"} tone="ok" />
        <Kpi label="باقٍ للمراجعة" value={(data?.total_items ?? 0) - (data?.approved ?? 0)} />
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-brand-50 text-brand-700">
            <tr>
              <th className="text-start p-3">الفئة</th>
              <th className="text-start p-3">الوصف</th>
              <th className="text-start p-3">الوحدة</th>
              <th className="text-start p-3">الكمية</th>
              <th className="text-start p-3">الثقة</th>
              <th className="text-start p-3">الحالة</th>
              <th className="text-start p-3">المصدر</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((i) => {
              const conf = Number(i.confidence);
              const qty = Number(i.quantity);
              const edited = i.original_quantity != null && Number(i.original_quantity) !== qty;
              return (
                <tr key={i.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 font-medium">{i.category}</td>
                  <td className="p-3 text-gray-600">{i.description || "—"}</td>
                  <td className="p-3">{i.unit}</td>
                  <td className="p-3">
                    {editing === i.id ? (
                      <input
                        type="number" step="0.001" className="border rounded px-2 py-1 w-28"
                        value={editQty} onChange={(e) => setEditQty(e.target.value)}
                        autoFocus
                      />
                    ) : (
                      <span>
                        {NUM3.format(qty)}
                        {edited && (
                          <span className="text-xs text-amber-600 ms-2">
                            (الأصلي: {NUM3.format(Number(i.original_quantity))})
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="p-3">
                    <span className={`dot ${confidenceClass(conf)}`}></span>
                    {(conf * 100).toFixed(0)}%
                  </td>
                  <td className="p-3 text-xs">{statusLabel(i.review_status)}</td>
                  <td className="p-3 text-xs text-gray-500">
                    {i.source_element_ids?.length
                      ? `${i.source_element_ids.length} عنصر`
                      : "—"}
                  </td>
                  <td className="p-3 text-end whitespace-nowrap">
                    {editing === i.id ? (
                      <>
                        <button onClick={async () => {
                          await patch(i.id, { quantity: Number(editQty) });
                          setEditing(null);
                        }} className="text-brand-500 text-sm me-2">حفظ</button>
                        <button onClick={() => setEditing(null)} className="text-gray-500 text-sm">إلغاء</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => { setEditing(i.id); setEditQty(String(qty)); }}
                                className="text-brand-500 text-sm me-2">✎</button>
                        <button onClick={() => patch(i.id, { review_status: "approved" })}
                                className="text-green-600 text-sm me-2">✓</button>
                        <button onClick={() => patch(i.id, { review_status: "rejected" })}
                                className="text-red-500 text-sm">✕</button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
            {data?.items.length === 0 && (
              <tr><td colSpan={8} className="p-6 text-center text-gray-400">
                لا توجد بنود بعد. ارفع مستندات IFC/PDF أولاً.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-500 mt-3">
        البنود ذات الثقة المنخفضة (نقطة حمراء/صفراء) تتطلب مراجعتك قبل التسعير.
        كل تعديل يُسجَّل في سجل التدقيق (audit log).
      </p>
    </Shell>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string | number; tone?: "ok" | "warn" }) {
  const color = tone === "ok" ? "text-green-700" : tone === "warn" ? "text-amber-700" : "text-brand-700";
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </div>
  );
}
