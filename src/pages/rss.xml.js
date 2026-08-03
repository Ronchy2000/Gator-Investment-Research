import rss from "@astrojs/rss";
import { getCollection } from "astro:content";
import { articleHref, sortArticles } from "../lib/articles";

export async function GET(context) {
  const articles = sortArticles(await getCollection("articles"));
  return rss({
    title: "获得信息差",
    description: "按日整理值得关注的市场信息与投资观察。",
    site: context.site,
    items: articles.map((article) => ({
      title: article.data.title,
      description: article.data.description,
      pubDate: article.data.publishedAt,
      link: articleHref(article),
      customData: `<source>${article.data.source}</source>`,
    })),
  });
}
