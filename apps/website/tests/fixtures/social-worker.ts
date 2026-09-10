// Test-only entrypoint: real auction, SQLite, R2 and publisher verification.
import api from "../../worker/api";
import { Auction as TestAuction } from "./auction-worker";
import type { Placement } from "../../src/lib/auction";
import type { Env } from "../../worker/env";
export default api;
export class Auction extends TestAuction {
  constructor(ctx: DurableObjectState, env: Env) {
    const bucket = env.ARTWORK;
    const artwork = new Proxy(bucket, {
      get(target, name) {
        if (name === "put")
          return async (...args: Parameters<R2Bucket["put"]>) => {
            if (String(args[0]).startsWith("social/")) {
              const gate = await fetch(`https://social-upload.test/${args[0]}`);
              if (!gate.ok) throw new Error("Simulated storage failure");
            }
            return target.put(...args);
          };
        const value = Reflect.get(target, name);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
    super(ctx, { ...env, ARTWORK: artwork });
  }
  testSeed(revision: number, placements: Record<string, Placement>) {
    this.ctx.storage.transactionSync(() => {
      this.ctx.storage.sql.exec("DELETE FROM placements; DELETE FROM bids;");
      for (const p of Object.values(placements)) {
        const token = p.textureUrl.slice("/api/artwork/".length, -4);
        this.ctx.storage.sql.exec(
          `INSERT INTO bids
          (id, request_id, slot_id, amount, brand, message, url, artwork_token, logo_token, status, created_at, published_at)
          VALUES (?,?,?,?,?,?,?,?,?,'won',?,?)`,
          p.id,
          p.id,
          p.slotId,
          p.amount,
          p.brand,
          p.message,
          p.url,
          token,
          token,
          p.publishedAt,
          p.publishedAt,
        );
        this.ctx.storage.sql.exec(
          "INSERT INTO placements VALUES (?,?)",
          p.slotId,
          p.id,
        );
      }
      this.ctx.storage.sql.exec(
        "UPDATE counters SET value = ? WHERE name = 'revision'",
        revision,
      );
    });
  }
}
