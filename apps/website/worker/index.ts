// @ts-ignore OpenNext generates this entry point during build:worker.
import next from "../.open-next/worker.js";
import api from "./api";
import type { Env } from "./env";
export { Auction } from "./auction";

export default {
  async scheduled(_event: ScheduledController, env: Env) {
    await env.AUCTION.get(
      env.AUCTION.idFromName("the-driving-fly-v1"),
    ).syncPageViews();
  },
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const url = new URL(request.url);
    if (url.hostname === "www.thedrivingfly.com") {
      url.hostname = "thedrivingfly.com";
      url.protocol = "https:";
      return Response.redirect(url.href, 308);
    }
    if (url.pathname.startsWith("/api/")) return api.fetch(request, env);
    // Previously shared image URLs resolve to the latest complete render when
    // fetched again. Third-party copies already cached cannot be revoked here.
    const oldSocial = /^\/social\/driving-fly-(wide|square)-v\d+\.jpg$/.exec(url.pathname);
    if (oldSocial && (request.method === "GET" || request.method === "HEAD")) {
      url.pathname = `/api/social/${oldSocial[1]}.jpg`;
      return api.fetch(new Request(url, request), env);
    }
    const response = await next.fetch(request, env, ctx);
    if (env.SITE_URL !== "https://thedrivingfly.com") {
      const headers = new Headers(response.headers);
      headers.set("X-Robots-Tag", "noindex, nofollow");
      return new Response(response.body, { status: response.status, headers });
    }
    return response;
  },
} satisfies ExportedHandler<Env>;
