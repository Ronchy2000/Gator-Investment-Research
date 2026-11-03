import snapshot from "../../statistics/visit-statistics.json";

export const prerender = true;

export function GET() {
  return new Response(JSON.stringify(snapshot), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
