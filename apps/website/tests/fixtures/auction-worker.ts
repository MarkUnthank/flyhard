// Only bundled by the integration suite. Never import this from a deployed entrypoint.
import { WorkerEntrypoint } from "cloudflare:workers";
import api from "../../worker/api";
import { Auction as ProductionAuction } from "../../worker/auction";
export default api;
export class Auction extends ProductionAuction {
  testSql(query: string, ...values: (string | number | null)[]) {
    return this.ctx.storage.sql.exec(query, ...values).toArray();
  }
  async testAlarm() {
    await this.alarm();
    return this.ctx.storage.getAlarm();
  }
  testConfig(test: boolean, recipient?: string) {
    this.env.STRIPE_API_KEY = test
      ? "sk_test_local_test_only"
      : "local_live_fixture";
    this.env.OUTBID_EMAIL_TEST_TO = recipient;
  }
}
export class TestEmail extends WorkerEntrypoint {
  async send(message: EmailMessageBuilder) {
    const response = await fetch("https://email.test/send", {
      method: "POST",
      body: JSON.stringify(message),
    });
    if (!response.ok) throw new Error("Simulated temporary email failure");
    return response.json();
  }
}
