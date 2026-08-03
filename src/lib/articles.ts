import type { CollectionEntry } from "astro:content";

export type ArticleEntry = CollectionEntry<"articles">;

export const ARTICLE_SOURCES = [
  {
    slug: "huode-xinxicha",
    name: "获得信息差",
    label: "每日信息",
    eyebrow: "DAILY INTELLIGENCE",
    description: "筛选值得关注的市场信息、行业变化与研究线索。",
  },
  {
    slug: "like-a-gator",
    name: "像鳄鱼一样思考",
    label: "每日复盘",
    eyebrow: "DAILY MARKET REVIEW",
    description: "记录交易日市场结构、情绪变化与操作思考。",
  },
] as const;

export type ArticleSource = (typeof ARTICLE_SOURCES)[number];

export function articleSource(sourceName: string): ArticleSource | undefined {
  return ARTICLE_SOURCES.find((source) => source.name === sourceName);
}

export function articleSourceSlug(article: ArticleEntry): string {
  return articleSource(article.data.source)?.slug || "wechat";
}

export function articlesFromSource(
  articles: ArticleEntry[],
  sourceName: string,
): ArticleEntry[] {
  return articles.filter((article) => article.data.source === sourceName);
}

export function sortArticles(articles: ArticleEntry[]): ArticleEntry[] {
  return [...articles].sort(
    (left, right) => right.data.publishedAt.getTime() - left.data.publishedAt.getTime(),
  );
}

export function articleHref(article: ArticleEntry): string {
  return `/articles/${article.id}/`;
}

export function formatDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}.${month}.${day}`;
}

export function formatMonth(value: Date): string {
  return `${value.getFullYear()}年${value.getMonth() + 1}月`;
}

export function monthKey(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}`;
}

export function plainText(value: string): string {
  return value
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/\s+/g, " ")
    .trim();
}

export function readingMinutes(body: string): number {
  const text = plainText(body);
  const hanCharacters = (text.match(/[\u3400-\u9fff]/g) || []).length;
  const words = text.replace(/[\u3400-\u9fff]/g, " ").split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.ceil((hanCharacters + words * 2) / 400));
}

export function isImageOnly(body: string): boolean {
  return plainText(body).length === 0 && /<img\b/i.test(body);
}
