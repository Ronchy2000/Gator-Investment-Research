export const VISIT_PROVIDER = "busuanzi.cc";
export const VISIT_SITE_URL = "https://gator.ronchy2000.top/";

export interface VisitCounts {
  siteUv: number;
  sitePv: number;
}

export interface VisitSnapshot extends VisitCounts {
  schemaVersion: 1;
  provider: typeof VISIT_PROVIDER;
  siteUrl: typeof VISIT_SITE_URL;
  updatedAt: string;
  source: "manual" | "api";
}

function parseCount(value: unknown): number | null {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && !/^\d+$/.test(value.trim())) return null;
  const count = Number(value);
  return Number.isSafeInteger(count) && count > 0 ? count : null;
}

export function readBusuanziCounts(value: unknown): VisitCounts | null {
  if (!value || typeof value !== "object") return null;
  const data = value as Record<string, unknown>;
  const siteUv = parseCount(data.busuanzi_site_uv);
  const sitePv = parseCount(data.busuanzi_site_pv);
  if (siteUv === null || sitePv === null || sitePv < siteUv) return null;
  return { siteUv, sitePv };
}

export function countsAtLeast(counts: VisitCounts, baseline: VisitCounts): boolean {
  return counts.siteUv >= baseline.siteUv && counts.sitePv >= baseline.sitePv;
}

export function snapshotTime(snapshot: VisitSnapshot): number {
  const timestamp = /^\d{4}-\d{2}-\d{2}$/.test(snapshot.updatedAt)
    ? `${snapshot.updatedAt}T00:00:00+08:00`
    : snapshot.updatedAt;
  return Date.parse(timestamp);
}

export function isVisitSnapshot(value: unknown): value is VisitSnapshot {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return (
    data.schemaVersion === 1 &&
    data.provider === VISIT_PROVIDER &&
    data.siteUrl === VISIT_SITE_URL &&
    (data.source === "manual" || data.source === "api") &&
    typeof data.updatedAt === "string" &&
    Number.isFinite(Date.parse(data.updatedAt)) &&
    typeof data.siteUv === "number" &&
    typeof data.sitePv === "number" &&
    readBusuanziCounts({ busuanzi_site_uv: data.siteUv, busuanzi_site_pv: data.sitePv }) !== null
  );
}

export function snapshotDate(snapshot: VisitSnapshot): string {
  // The bootstrap record has day precision because it was supplied manually.
  if (/^\d{4}-\d{2}-\d{2}$/.test(snapshot.updatedAt)) return snapshot.updatedAt;
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(snapshot.updatedAt));
}
