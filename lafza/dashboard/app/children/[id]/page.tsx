"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  approvePlan,
  Child,
  fetchChild,
  fetchHeatmap,
  fetchPlans,
  HeatmapCell,
  TreatmentPlan,
} from "@/lib/api";

/** MVP letters in the §7 developmental order (easier first). */
const MVP_LETTERS = ["ك", "ل", "ج", "ش", "س", "ق", "ر", "ص", "ط", "ث", "ذ", "غ"];
const POSITIONS = ["initial", "medial", "final"] as const;
const POSITION_AR: Record<string, string> = {
  initial: "بداية",
  medial: "وسط",
  final: "نهاية",
};

/** GOP → cell color: ≥85 discharge-green, ≥70 good, ≥50 working, <50 alert. */
function cellClasses(gop: number | undefined): string {
  if (gop === undefined) return "bg-gray-100 text-gray-300";
  if (gop >= 85) return "bg-[#2FA66A] text-white";
  if (gop >= 70) return "bg-[#0F6E6B] text-white";
  if (gop >= 50) return "bg-[#F2A93B] text-[#1B2A4A]";
  return "bg-[#E2574C] text-white";
}

function Heatmap({ cells }: { cells: HeatmapCell[] }) {
  const byCell = new Map(
    cells.map((c) => [`${c.phoneme}|${c.position}`, c]),
  );
  return (
    <div className="overflow-x-auto rounded-2xl bg-white p-4 shadow-sm">
      <table className="w-full border-separate border-spacing-1 text-center">
        <thead>
          <tr>
            <th className="px-2 text-sm text-gray-500">الحرف</th>
            {POSITIONS.map((p) => (
              <th key={p} className="px-2 text-sm text-gray-500">
                {POSITION_AR[p]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {MVP_LETTERS.map((letter) => (
            <tr key={letter}>
              <td className="text-lg font-bold">{letter}</td>
              {POSITIONS.map((position) => {
                const cell = byCell.get(`${letter}|${position}`);
                return (
                  <td
                    key={position}
                    title={
                      cell
                        ? `${cell.gop_score}${cell.error_type ? ` · ${cell.error_type}` : ""}`
                        : "لم يُقيَّم"
                    }
                    className={`h-10 w-20 rounded-lg text-sm font-bold ${cellClasses(cell?.gop_score)}`}
                  >
                    {cell ? cell.gop_score : "·"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-gray-600">
        <span><i className="ml-1 inline-block h-3 w-3 rounded bg-[#2FA66A]" />≥85 إتقان</span>
        <span><i className="ml-1 inline-block h-3 w-3 rounded bg-[#0F6E6B]" />70–84 جيد</span>
        <span><i className="ml-1 inline-block h-3 w-3 rounded bg-[#F2A93B]" />50–69 قيد العلاج</span>
        <span><i className="ml-1 inline-block h-3 w-3 rounded bg-[#E2574C]" />&lt;50 ضعيف</span>
        <span><i className="ml-1 inline-block h-3 w-3 rounded bg-gray-100" />لم يُقيَّم</span>
      </div>
    </div>
  );
}

function PlanCard({
  plan,
  onApprove,
  approving,
}: {
  plan: TreatmentPlan;
  onApprove: (id: string) => void;
  approving: boolean;
}) {
  const statusLabels: Record<string, string> = {
    draft: "مسودة — بانتظار الاعتماد",
    approved: "معتمدة",
    active: "نشطة",
  };
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-500">
            {plan.author === "ai" ? "مولّدة آليًا" : "من الأخصائي"} ·{" "}
            {new Date(plan.created_at).toLocaleDateString("ar")}
          </span>
          <span
            className={`rounded-full px-3 py-1 text-sm font-bold ${
              plan.status === "approved"
                ? "bg-[#2FA66A]/15 text-[#1d6b43]"
                : plan.status === "draft"
                  ? "bg-[#F2A93B]/15 text-[#8a5a00]"
                  : "bg-[#0F6E6B]/15 text-[#0F6E6B]"
            }`}
            data-testid="plan-status"
          >
            {statusLabels[plan.status]}
          </span>
        </div>
        {plan.status === "draft" && (
          <button
            onClick={() => onApprove(plan.id)}
            disabled={approving}
            className="rounded-xl bg-[#0F6E6B] px-5 py-2 font-bold text-white transition hover:bg-[#0c5856] disabled:opacity-50"
          >
            {approving ? "جارٍ الاعتماد…" : "اعتماد الخطة"}
          </button>
        )}
      </div>
      <div className="mb-3 flex gap-2">
        {plan.target_phonemes.map((p) => (
          <span
            key={p}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#0F6E6B] text-lg font-bold text-white"
          >
            {p}
          </span>
        ))}
      </div>
      <ul className="space-y-1 text-sm text-gray-700">
        {plan.goals.map((g) => (
          <li key={g.phoneme}>• {g.description_ar}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ChildProfilePage() {
  const { id } = useParams<{ id: string }>();
  const [child, setChild] = useState<Child | null>(null);
  const [cells, setCells] = useState<HeatmapCell[] | null>(null);
  const [plans, setPlans] = useState<TreatmentPlan[] | null>(null);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    Promise.all([fetchChild(id), fetchHeatmap(id), fetchPlans(id)])
      .then(([c, h, p]) => {
        setChild(c);
        setCells(h.cells);
        setPlans(p);
      })
      .catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(load, [load]);

  const handleApprove = async (planId: string) => {
    setApprovingId(planId);
    try {
      await approvePlan(planId);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApprovingId(null);
    }
  };

  if (error)
    return (
      <p className="rounded-xl bg-[#E2574C]/10 p-4 text-[#E2574C]">
        خطأ: {error}
      </p>
    );
  if (!child || !cells || !plans)
    return <p className="text-gray-500">جارٍ التحميل…</p>;

  return (
    <section className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-[#0F6E6B] hover:underline">
          ← قائمة الحالات
        </Link>
        <h1 className="mt-2 text-2xl font-bold">
          ملف الطفل{" "}
          <span className="font-mono text-lg text-gray-500">
            {child.id.slice(0, 8)}
          </span>
        </h1>
        <p className="text-gray-600">
          {child.sex === "male" ? "ذكر" : "أنثى"} · مواليد {child.dob} · لهجة{" "}
          {child.dialect}
        </p>
      </div>

      <div>
        <h2 className="mb-3 text-xl font-bold">
          خريطة الحروف <span className="text-sm font-normal text-gray-500">(آخر درجة لكل حرف × موضع)</span>
        </h2>
        <Heatmap cells={cells} />
      </div>

      <div>
        <h2 className="mb-3 text-xl font-bold">الخطط العلاجية</h2>
        {plans.length === 0 ? (
          <p className="text-gray-500">لا خطط بعد</p>
        ) : (
          <div className="space-y-4">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                onApprove={handleApprove}
                approving={approvingId === plan.id}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
