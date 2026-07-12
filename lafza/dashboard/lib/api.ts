const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000/api/v1";

export type CaseloadRow = {
  child_id: string;
  dob: string;
  sex: string;
  dialect: string;
  attempts: number;
  adherence: number; // 0..1 — practiced days / 7
  gop_mean: number | null;
  gop_delta_30d: number | null;
  plan_status: string | null;
  last_activity_at: string | null;
};

export type HeatmapCell = {
  phoneme: string;
  position: "initial" | "medial" | "final";
  gop_score: number;
  error_type: string | null;
  created_at: string;
};

export type Child = {
  id: string;
  dob: string;
  sex: string;
  dialect: string;
  created_at: string;
};

export type TreatmentPlan = {
  id: string;
  child_id: string;
  author: string;
  goals: {
    phoneme: string;
    baseline_gop: number;
    target_gop: number;
    description_ar: string;
  }[];
  target_phonemes: string[];
  status: "draft" | "approved" | "active";
  approved_by: string | null;
  created_at: string;
};

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!resp.ok) throw new Error(`GET ${path} → ${resp.status}`);
  return resp.json();
}

export const fetchCaseload = () => get<CaseloadRow[]>("/therapist/caseload");
export const fetchChild = (id: string) => get<Child>(`/children/${id}`);
export const fetchHeatmap = (id: string) =>
  get<{ child_id: string; cells: HeatmapCell[] }>(
    `/children/${id}/phoneme-heatmap`,
  );
export const fetchPlans = (childId: string) =>
  get<TreatmentPlan[]>(`/treatment-plans?child_id=${childId}`);

/** DEV bootstrap: a demo SLP identity for plan approval until auth lands.
 *  Cached in localStorage; recreated if the backend no longer knows it. */
async function ensureDemoSlp(): Promise<string> {
  const cached =
    typeof window !== "undefined" ? localStorage.getItem("lafza-slp-id") : null;
  if (cached) {
    const check = await fetch(`${API_BASE}/users/${cached}`);
    if (check.ok) return cached;
  }
  const resp = await fetch(`${API_BASE}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role: "slp",
      email: `slp-demo-${Date.now()}@lafza.dev`,
      password: "demo-pass-123",
    }),
  });
  if (!resp.ok) throw new Error(`SLP bootstrap failed (${resp.status})`);
  const slp = (await resp.json()) as { id: string };
  localStorage.setItem("lafza-slp-id", slp.id);
  return slp.id;
}

/** draft → approved, stamped with the approving SLP. */
export async function approvePlan(planId: string): Promise<TreatmentPlan> {
  const slpId = await ensureDemoSlp();
  const resp = await fetch(`${API_BASE}/treatment-plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "approved", approved_by: slpId }),
  });
  if (!resp.ok) throw new Error(`approve failed (${resp.status})`);
  return resp.json();
}
