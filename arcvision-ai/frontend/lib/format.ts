export const SAR = new Intl.NumberFormat("ar-SA", {
  style: "currency",
  currency: "SAR",
  maximumFractionDigits: 0,
});

export const NUM3 = new Intl.NumberFormat("ar-SA", { maximumFractionDigits: 3 });
export const PCT = new Intl.NumberFormat("ar-SA", { style: "percent", maximumFractionDigits: 1 });

export function confidenceClass(c: number) {
  if (c >= 0.9) return "dot-high";
  if (c >= 0.75) return "dot-mid";
  return "dot-low";
}

export function statusLabel(s: string): string {
  return {
    uploaded: "مرفوع",
    classified: "مُصنّف",
    processing: "جارٍ التحليل",
    ready_for_review: "جاهز للمراجعة",
    error: "خطأ",
    pending: "قيد المراجعة",
    approved: "معتمد",
    edited: "مُعدّل",
    rejected: "مرفوض",
    draft: "مسودة",
    priced: "مُسعّر",
    review: "مراجعة",
    tendered: "في المناقصة",
  }[s] || s;
}
