// Claude Code PreToolUse hook: block edits to official TechJam artifacts.
// Competition rules: participants must NOT modify the evaluator or public labels.
// Exit code 2 blocks the tool call; any other exit lets it proceed.
import { readFileSync } from "node:fs";

const input = JSON.parse(readFileSync(0, "utf8"));
const path = String(input?.tool_input?.file_path ?? "");
const isProtected =
  /^(evaluator|data)\//.test(path) || /^results\.json(\/|$)/.test(path);

if (isProtected) {
  console.error(
    `[hook] BLOCKED edit of "${path}": official TechJam artifact ` +
      `(evaluator/, data/, results.json) — competition rules forbid modifying it. ` +
      `Work around only with explicit human approval.`
  );
  process.exit(2);
}
