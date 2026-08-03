import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://gator.ronchy2000.top",
  output: "static",
  trailingSlash: "always",
  integrations: [
    sitemap({
      filter: (page) =>
        !["/all-reports/", "/macro-analysis/", "/industry-analysis/", "/investment-notes/"].some(
          (legacyPath) => page.includes(legacyPath),
        ),
    }),
  ],
});
