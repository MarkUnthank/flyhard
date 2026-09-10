import type { Env } from "./env";
import { legacySocialAlias } from "../src/lib/social";
export { Auction } from "./auction";
export default {
  fetch(request: Request, env: Env) {
    const url = new URL(request.url);
    const alias = legacySocialAlias(url.pathname);
    if (alias && (request.method === "GET" || request.method === "HEAD")) {
      url.pathname = alias;
      request = new Request(url, request);
    }
    return env.AUCTION.get(env.AUCTION.idFromName("the-driving-fly-v1")).fetch(
      request,
    );
  },
} satisfies ExportedHandler<Env>;
