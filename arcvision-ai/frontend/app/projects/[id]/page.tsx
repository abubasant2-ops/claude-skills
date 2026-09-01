"use client";

import Link from "next/link";
import useSWR from "swr";
import Shell from "@/components/Shell";
import { apiFetch, API_URL, getToken } from "@/lib/api";
import { SAR, statusLabel } from "@/lib/format";

interface ProjectDetail {
  id: string;
  name: string;
  client_name?: string | null;
  location_city?: string | null;
  project_type?: string | null;
  gross_area_m2?: number | null;
  status: string;
}

interface DocItem {
  id: string;
  file_name: string;
  file_type: string;
  discipline?: string | null;
  status: string;
  page_count?: number | null;
  processing_meta?: { elements_extracted?: number } | null;
  error_message?: string | null;
}

const fetcher = <T,>(p: string) => apiFetch<T>(p);

export default function ProjectDetailPage({ params }: { params: { id: string } }) {
  const { data: project } = useSWR<ProjectDetail>(`/v1/projects/${params.id}`, fetcher);
  const { data: docs, mutate } = useSWR<DocItem[]>(
    `/v1/projects/${params.id}/documents`,
    fetcher,
    { refreshInterval: 3000 }, // poll while documents are processing
  );

  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    await fetch(`${API_URL}/v1/projects/${params.id}/documents`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: fd,
    });
    mutate();
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach(upload);
    e.target.value = "";
  };

  return (
    <Shell>
      <div className="flex items-center gap-3 mb-1">
        <Link href="/dashboard" className="text-sm text-brand-500 hover:underline">← لوحة القيادة</Link>
      </div>
      <h1 className="text-2xl font-bold">{project?.name ?? "..."}</h1>
      <p className="text-sm text-gray-500 mb-6">
        {project?.client_name} · {project?.location_city} · {project?.gross_area_m2 ?? "—"} م² ·
        <span className="ms-1">{project ? statusLabel(project.status) : ""}</span>
      </p>

      <div className="grid md:grid-cols-3 gap-4 mb-6">
        <Link href={`/projects/${params.id}/takeoff`}
              className="bg-white rounded-xl p-5 shadow-sm hover:shadow-md transition">
          <div className="text-xs text-gray-500">الخطوة 2</div>
          <div className="font-bold text-brand-700 text-lg">مراجعة الحصر</div>
          <div className="text-xs text-gray-500 mt-1">راجع الكميات منخفضة الثقة واعتمدها.</div>
        </Link>
        <Link href={`/projects/${params.id}/cost`}
              className="bg-white rounded-xl p-5 shadow-sm hover:shadow-md transition">
          <div className="text-xs text-gray-500">الخطوة 3</div>
          <div className="font-bold text-brand-700 text-lg">محرك التكلفة</div>
          <div className="text-xs text-gray-500 mt-1">حساب المباشرة، الطوارئ، الهامش، م².</div>
        </Link>
        <a href={`${API_URL}/v1/projects/${params.id}/reports/boq.xlsx`}
           target="_blank" rel="noopener"
           className="bg-white rounded-xl p-5 shadow-sm hover:shadow-md transition">
          <div className="text-xs text-gray-500">المخرَج</div>
          <div className="font-bold text-brand-700 text-lg">تصدير BOQ (xlsx)</div>
          <div className="text-xs text-gray-500 mt-1">جدول كميات + ملخص مالي.</div>
        </a>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
        <h2 className="font-bold mb-3">رفع المستندات</h2>
        <label className="block border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:bg-gray-50">
          <span className="text-gray-600 text-sm">
            اسحب وأفلت الملفات هنا أو
            <span className="text-brand-500 underline mx-1">تصفّح</span>
            <br/>
            <span className="text-xs text-gray-400">PDF · IFC · BOQ (xlsx)</span>
          </span>
          <input type="file" multiple className="hidden" onChange={onPick}
                 accept=".pdf,.ifc,.xlsx,.xls,.csv" />
        </label>

        <div className="mt-4 space-y-2">
          {docs?.length === 0 && <p className="text-sm text-gray-400">لا توجد مستندات بعد.</p>}
          {docs?.map((d) => (
            <div key={d.id} className="flex items-center gap-3 text-sm p-2 rounded bg-gray-50">
              <span className="w-12 text-center text-brand-500 font-mono uppercase">{d.file_type}</span>
              <span className="flex-1 truncate">{d.file_name}</span>
              <span className="text-xs text-gray-500">{d.discipline || "—"}</span>
              <StatusBadge status={d.status} />
              <span className="text-xs text-gray-500">
                {d.processing_meta?.elements_extracted != null
                  ? `${d.processing_meta.elements_extracted} عنصر`
                  : d.page_count ? `${d.page_count} صفحة` : ""}
              </span>
              {d.error_message && <span className="text-xs text-red-600">{d.error_message}</span>}
            </div>
          ))}
        </div>
      </div>
    </Shell>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color = {
    ready_for_review: "bg-green-100 text-green-700",
    processing: "bg-amber-100 text-amber-700",
    error: "bg-red-100 text-red-700",
  }[status] || "bg-gray-100 text-gray-700";
  return <span className={`text-xs px-2 py-0.5 rounded ${color}`}>{statusLabel(status)}</span>;
}
