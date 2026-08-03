import type { CollectionEntry } from "astro:content";

export type ReportEntry = CollectionEntry<"reports">;

export const REPORT_CATEGORIES = ["宏观分析", "行业分析", "其他"] as const;

export function sortReports(reports: ReportEntry[]): ReportEntry[] {
  return [...reports].sort((left, right) => {
    const dateDifference = right.data.publishedAt.getTime() - left.data.publishedAt.getTime();
    return dateDifference || right.data.reportId - left.data.reportId;
  });
}

export function reportHref(report: ReportEntry): string {
  return `/reports/${report.data.reportId}/`;
}

export function reportYear(report: ReportEntry): string {
  return String(report.data.publishedAt.getFullYear());
}
