import { appendFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import {
  countsAtLeast,
  isVisitSnapshot,
  readBusuanziCounts,
  snapshotDate,
  VISIT_PROVIDER,
  VISIT_SITE_URL,
} from "../src/lib/visit-statistics.ts";

const root = fileURLToPath(new URL("../", import.meta.url));
const snapshotPath = join(root, "statistics/visit-statistics.json");
const historyDirectory = join(root, "statistics/visit-history");
const endpoint = "https://cdn.busuanzi.cc/api.php";
const maxAttempts = 3;
const requestTimeout = 15_000;
const runUrl = process.env.GITHUB_RUN_ID
  ? `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
  : null;

async function writeSummary(content) {
  if (process.env.GITHUB_STEP_SUMMARY) {
    await appendFile(process.env.GITHUB_STEP_SUMMARY, content);
  }
}

function errorMessage(error) {
  if (error instanceof Error && error.cause instanceof Error) {
    return `${error.message}: ${error.cause.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

async function main() {
  const previous = JSON.parse(await readFile(snapshotPath, "utf8"));
  if (!isVisitSnapshot(previous)) {
    throw new Error("已保存的访问统计格式无效；停止采集，避免覆盖备份，请从 Git 历史恢复该文件。");
  }

  let latest = previous;
  let lastError = null;
  const attempts = [];

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      // Match the existing 3.6.9 browser script's POST body and site identity.
      // This endpoint records a visit as well as returning the site's counters.
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "text/plain;charset=UTF-8",
          Origin: new URL(VISIT_SITE_URL).origin,
          Referer: VISIT_SITE_URL,
        },
        body: JSON.stringify({ url: VISIT_SITE_URL, referrer: "" }),
        signal: AbortSignal.timeout(requestTimeout),
        redirect: "error",
      });
      if (!response.ok) throw new Error(`统计接口返回 HTTP ${response.status}`);

      const counts = readBusuanziCounts(await response.json());
      if (!counts) throw new Error("统计接口没有返回有效的全站 UV/PV（必须为正整数，且 PV ≥ UV）");
      if (!countsAtLeast(counts, previous)) {
        throw new Error(
          `计数倒退：接口 UV=${counts.siteUv}、PV=${counts.sitePv}；已保存 UV=${previous.siteUv}、PV=${previous.sitePv}`,
        );
      }

      const checkedAt = new Date().toISOString();
      latest = { ...previous, ...counts, source: "api", updatedAt: checkedAt };
      attempts.push({ attempt, checkedAt, status: "success", ...counts });
      lastError = null;
      break;
    } catch (error) {
      lastError = errorMessage(error);
      attempts.push({ attempt, checkedAt: new Date().toISOString(), status: "failure", error: lastError });
      console.warn(`访问统计采集 ${attempt}/${maxAttempts} 失败：${lastError}`);
      if (attempt < maxAttempts) await delay(5_000);
    }
  }

  const checkedAt = new Date().toISOString();
  const status = lastError === null ? "success" : "failure";
  const lastCheck = { checkedAt, status, attempts: attempts.length, error: lastError, runUrl };
  const record = {
    checkedAt,
    provider: VISIT_PROVIDER,
    siteUrl: VISIT_SITE_URL,
    status,
    snapshot: {
      updatedAt: latest.updatedAt,
      source: latest.source,
      siteUv: latest.siteUv,
      sitePv: latest.sitePv,
    },
    attempts,
    error: lastError,
    runUrl,
  };

  await mkdir(historyDirectory, { recursive: true });
  const month = snapshotDate({ ...latest, updatedAt: checkedAt }).slice(0, 7);
  await appendFile(join(historyDirectory, `${month}.jsonl`), `${JSON.stringify(record)}\n`);
  const temporaryPath = `${snapshotPath}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify({ ...latest, lastCheck }, null, 2)}\n`);
  await rename(temporaryPath, snapshotPath);

  const summary = [
    "## 每日访问统计备份",
    "",
    `- 采集时间：${checkedAt}`,
    `- 采集结果：${status === "success" ? "成功，已更新备份" : "失败，保留上次有效计数"}`,
    `- 累计访客：${latest.siteUv}`,
    `- 累计浏览：${latest.sitePv}`,
    `- 有效计数保存时间：${latest.updatedAt}（${latest.source === "manual" ? "手动记录" : "原统计接口"}）`,
    `- 请求次数：${attempts.length}`,
    `- 每次尝试和故障原因见 statistics/visit-history/${month}.jsonl`,
    "",
  ];
  if (lastError) summary.push("采集错误：", "", "```text", lastError, "```", "");
  await writeSummary(`${summary.join("\n")}\n`);
  console.log(`已保存 ${status} 记录；当前备份 UV=${latest.siteUv}、PV=${latest.sitePv}（${latest.updatedAt}）。`);
  if (lastError) process.exitCode = 1;
}

main().catch(async (error) => {
  const message = errorMessage(error);
  console.error(message);
  process.exitCode = 1;
  await writeSummary(`## 访问统计备份未完成\n\n\`\`\`text\n${message}\n\`\`\`\n`);
});
