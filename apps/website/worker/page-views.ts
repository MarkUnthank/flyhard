import { z } from "zod";

export const ANALYTICS_START = Date.parse("2026-09-09T00:00:00Z");
export const DAY = 86_400_000;
const responseSchema = z.object({
  errors: z.array(z.unknown()).nullish(),
  data: z
    .object({
      viewer: z.object({
        accounts: z
          .array(
            z.object({
              rumPageloadEventsAdaptiveGroups: z.array(
                z.object({
                  count: z.number().int().nonnegative().safe(),
                  dimensions: z.object({ date: z.iso.date() }),
                }),
              ),
            }),
          )
          .length(1),
      }),
    })
    .nullable(),
});

// Cloudflare's count is already sampling-adjusted. Do not multiply it by sampleInterval.
export async function fetchPageViews(token: string, from: number, to: number) {
  const response = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    signal: AbortSignal.timeout(20_000),
    body: JSON.stringify({
      query: `query PageViews($from: Time!, $to: Time!) {
        viewer { accounts(filter: {accountTag: "94f9d97fe2538adb3efe55c05b63637d"}) {
          rumPageloadEventsAdaptiveGroups(limit: 8, filter: {
            datetime_geq: $from, datetime_lt: $to,
            siteTag: "a9425d0f08934c0b919b4c5ff11fb5f7", bot: 0
          }) { count dimensions { date } }
        } }
      }`,
      variables: {
        from: new Date(from).toISOString(),
        to: new Date(to).toISOString(),
      },
    }),
  });
  if (!response.ok) throw new Error(`Web Analytics HTTP ${response.status}`);
  const result = responseSchema.parse(await response.json());
  if (result.errors?.length || !result.data)
    throw new Error("Web Analytics query failed");
  const days = new Map<string, number>();
  for (let day = from; day < to; day += DAY) {
    days.set(new Date(day).toISOString().slice(0, 10), 0);
  }
  for (const row of result.data.viewer.accounts[0]
    .rumPageloadEventsAdaptiveGroups) {
    if (!days.has(row.dimensions.date))
      throw new Error("Unexpected analytics date");
    days.set(row.dimensions.date, row.count);
  }
  return days;
}
