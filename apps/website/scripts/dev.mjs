import { spawn } from "node:child_process";
import { localStripe } from "./local-stripe.mjs";
localStripe();
const children = [
  spawn(
    "npx",
    ["wrangler", "dev", "-c", "wrangler.dev.jsonc", "--port", "8788"],
    { stdio: "inherit" },
  ),
  spawn("npx", ["next", "dev", "--port", "3000"], { stdio: "inherit" }),
];
let exiting = false;
function stop(code = 0) {
  if (exiting) return;
  exiting = true;
  children.forEach((child) => child.kill("SIGTERM"));
  process.exitCode = code;
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
children.forEach((child) => child.on("exit", (code) => stop(code ?? 0)));
