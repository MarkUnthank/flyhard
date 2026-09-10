import type { Env } from "./env";
export { Auction } from "./auction";
export default {
  fetch(request: Request, env: Env) {
    return env.AUCTION.get(env.AUCTION.idFromName("the-driving-fly-v1")).fetch(
      request,
    );
  },
} satisfies ExportedHandler<Env>;
