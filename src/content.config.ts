import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const articles = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/articles" }),
  schema: z.object({
    title: z.string(),
    publishedAt: z.coerce.date(),
    source: z.string(),
    sourceUrl: z.string().url(),
    description: z.string().default(""),
    cover: z.string().default(""),
    articleId: z.string(),
  }),
});

const reports = defineCollection({
  loader: glob({
    pattern: "**/*.md",
    base: "./src/content/reports",
    deferRender: true,
  }),
  schema: z.object({
    title: z.string(),
    publishedAt: z.coerce.date(),
    source: z.string(),
    sourceUrl: z.string().url(),
    description: z.string().default(""),
    category: z.enum(["宏观分析", "行业分析", "其他"]),
    reportId: z.number().int().positive(),
    legacyStem: z.string(),
  }),
});

const notes = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/notes" }),
  schema: z.object({
    title: z.string(),
    publishedAt: z.coerce.date(),
    description: z.string(),
    noteType: z.string(),
    cover: z.string().default(""),
  }),
});

export const collections = { articles, reports, notes };
