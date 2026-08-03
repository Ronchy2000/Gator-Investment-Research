import rss from "@astrojs/rss";
import { getCollection } from "astro:content";
import { articleHref, sortArticles } from "../lib/articles";

export async function GET(context) {
  const articles = sortArticles(await getCollection("articles"));
  return rss({
    title: "鳄鱼派投资档案",
    description: "按日归档获得信息差与像鳄鱼一样思考：每日信息、市场复盘与投资观察。",
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
