"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CaseloadRow, fetchCaseload } from "@/lib/api";

function ageLabel(dob: string): string {
  const months =
    (Date.now() - new Date(dob).getTime()) / (1000 * 60 * 60 * 24 * 30.44);
  const years = Math.floor(months / 12);
  const rest = Math.round(months % 12);
  return `${years} س ${rest} ش`;
}

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-gray-400">—</span>;
  if (delta === 0) return <span className="text-gray-500">0</span>;
  const up = delta > 0;
  return (
    <span
      className={`inline-flex items-center gap-1 font-bold ${
        up ? "text-[#2FA66A]" : "text-[#E2574C]"
      }`}
    >
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  );
}

function PlanStatusChip({ status }: { status: string | null }) {
  if (!status) return <span className="text-gray-400">لا خطة</span>;
  const styles: Record<string, string> = {
    draft: "bg-[#F2A93B]/15 text-[#8a5a00]",
    approved: "bg-[#2FA66A]/15 text-[#1d6b43]",
    active: "bg-[#0F6E6B]/15 text-[#0F6E6B]",
  };
  const labels: Record<string, string> = {
    draft: "مسودة",
    approved: "معتمدة",
    active: "نشطة",
  };
  return (
    <span
      className={`rounded-full px-3 py-1 text-sm font-bold ${styles[status] ?? ""}`}
    >
      {labels[status] ?? status}
    </span>
  );
}

export default function CaseloadPage() {
  const [rows, setRows] = useState<CaseloadRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCaseload()
      .then(setRows)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error)
    return (
      <p className="rounded-xl bg-[#E2574C]/10 p-4 text-[#E2574C]">
        تعذّر الاتصال بالخادم: {error}
      </p>
    );
  if (!rows) return <p className="text-gray-500">جارٍ التحميل…</p>;

  return (
    <section>
      <h1 className="mb-6 text-2xl font-bold">
        قائمة الحالات{" "}
        <span className="text-base font-normal text-gray-500">
          ({rows.length} طفل)
        </span>
      </h1>
      <div className="overflow-x-auto rounded-2xl bg-white shadow-sm">
        <table className="w-full text-right">
          <thead className="border-b bg-[#0F6E6B] text-sm text-white">
            <tr>
              <th className="px-4 py-3 font-bold">الطفل</th>
              <th className="px-4 py-3 font-bold">العمر</th>
              <th className="px-4 py-3 font-bold">المحاولات</th>
              <th className="px-4 py-3 font-bold">الالتزام (٧ أيام)</th>
              <th className="px-4 py-3 font-bold">متوسط الدرجة</th>
              <th className="px-4 py-3 font-bold">Δ الدرجة (٣٠ يوم)</th>
              <th className="px-4 py-3 font-bold">الخطة</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.child_id}
                className="border-b last:border-0 hover:bg-[#FAF8F4]"
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/children/${row.child_id}`}
                    className="font-bold text-[#0F6E6B] underline-offset-4 hover:underline"
                  >
                    {row.child_id.slice(0, 8)}
                  </Link>
                  <span className="mr-2 text-sm text-gray-500">
                    {row.sex === "male" ? "ذكر" : "أنثى"} · {row.dialect}
                  </span>
                </td>
                <td className="px-4 py-3">{ageLabel(row.dob)}</td>
                <td className="px-4 py-3">{row.attempts}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-200">
                      <div
                        className="h-full rounded-full bg-[#0F6E6B]"
                        style={{ width: `${Math.round(row.adherence * 100)}%` }}
                      />
                    </div>
                    <span className="text-sm">
                      {Math.round(row.adherence * 100)}٪
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 font-bold">{row.gop_mean ?? "—"}</td>
                <td className="px-4 py-3">
                  <DeltaBadge delta={row.gop_delta_30d} />
                </td>
                <td className="px-4 py-3">
                  <PlanStatusChip status={row.plan_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-6 text-center text-gray-500">لا حالات بعد</p>
        )}
      </div>
    </section>
  );
}
