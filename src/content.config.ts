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

export const collections = { articles };
