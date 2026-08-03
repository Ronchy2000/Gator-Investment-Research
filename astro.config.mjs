import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://gator.ronchy2000.top",
  output: "static",
  trailingSlash: "always",
  integrations: [sitemap()],
});
