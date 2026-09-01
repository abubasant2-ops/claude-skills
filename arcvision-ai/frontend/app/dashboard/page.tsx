"use client";

import Link from "next/link";
import useSWR from "swr";
import Shell from "@/components/Shell";
import { apiFetch } from "@/lib/api";
import { SAR, statusLabel } from "@/lib/format";

interface Project {
  id: string;
  name: string;
  client_name?: string | null;
  project_type?: string | null;
  location_city?: string | null;
  gross_area_m2?: number | null;
  status: string;
  created_at: string;
}

const fetcher = (path: string) => apiFetch<Project[]>(path);

export default function DashboardPage() {
  const { data, error, isLoading } = useSWR("/v1/projects", fetcher);

  return (
    <Shell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">لوحة القيادة</h1>
        <Link
          href="/projects/new"
          className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-2 rounded-lg text-sm"
        >
          + مشروع جديد
        </Link>
      </div>

      {/* KPI cards (computed once data is loaded) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Kpi label="مشاريع نشطة" value={data?.length ?? "—"} />
        <Kpi label="مسوّدات" value={data?.filter((p) => p.status === "draft").length ?? "—"} />
        <Kpi label="تحت المراجعة" value={data?.filter((p) => p.status === "review").length ?? "—"} />
        <Kpi label="مُسعّرة" value={data?.filter((p) => p.status === "priced").length ?? "—"} />
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-brand-50 text-brand-700">
            <tr>
              <th className="text-start p-3">المشروع</th>
              <th className="text-start p-3">العميل</th>
              <th className="text-start p-3">المدينة</th>
              <th className="text-start p-3">المساحة م²</th>
              <th className="text-start p-3">الحالة</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="p-6 text-center text-gray-400">جارٍ التحميل...</td></tr>
            )}
            {error && (
              <tr><td colSpan={6} className="p-6 text-center text-red-600">تعذّر التحميل</td></tr>
            )}
            {data?.length === 0 && (
              <tr><td colSpan={6} className="p-6 text-center text-gray-400">
                لا توجد مشاريع بعد. ابدأ بإنشاء أول مشروع.
              </td></tr>
            )}
            {data?.map((p) => (
              <tr key={p.id} className="border-t hover:bg-gray-50">
                <td className="p-3">
                  <Link href={`/projects/${p.id}`} className="text-brand-700 hover:underline">
                    {p.name}
                  </Link>
                </td>
                <td className="p-3">{p.client_name || "—"}</td>
                <td className="p-3">{p.location_city || "—"}</td>
                <td className="p-3">{p.gross_area_m2 ?? "—"}</td>
                <td className="p-3">{statusLabel(p.status)}</td>
                <td className="p-3 text-end">
                  <Link href={`/projects/${p.id}`} className="text-sm text-brand-500 hover:underline">فتح ←</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-2xl font-bold text-brand-700">{value}</div>
    </div>
  );
}
