import { getCollection } from "astro:content";
import { articleHref, formatDate, plainText, sortArticles } from "../lib/articles";
import { reportHref, sortReports } from "../lib/reports";

export const prerender = true;

export async function GET() {
  const [articles, reports, notes] = await Promise.all([
    getCollection("articles"),
    getCollection("reports"),
    getCollection("notes"),
  ]);
  const items = [
    ...sortArticles(articles).map((article) => ({
      title: article.data.title,
      description: article.data.description,
      date: formatDate(article.data.publishedAt),
      href: articleHref(article),
      text: plainText(article.body || ""),
      kind: "wechat",
      label: "公众号",
    })),
    ...sortReports(reports).map((report) => ({
      title: report.data.title,
      description: report.data.description,
      date: formatDate(report.data.publishedAt),
      href: reportHref(report),
      text: plainText(report.body || ""),
      kind: "report",
      label: report.data.category,
    })),
    ...notes.map((note) => ({
      title: note.data.title,
      description: note.data.description,
      date: formatDate(note.data.publishedAt),
      href: `/notes/${note.id}/`,
      text: plainText(note.body || ""),
      kind: "note",
      label: "投资随笔",
    })),
  ];
  return new Response(JSON.stringify(items), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
