import { z } from "zod";

export const ANALYTICS_START = Date.parse("2026-09-09T00:00:00Z");
export const DAY = 86_400_000;
const responseSchema = z.object({
  errors: z.array(z.unknown()).nullish(),
  data: z
    .object({
      viewer: z.object({
        zones: z
          .array(
            z.object({
              httpRequests1dGroups: z.array(
                z.object({
                  sum: z.object({
                    requests: z.number().int().nonnegative().safe(),
                  }),
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

// Zone HTTP totals include repeat requests, assets, API calls and bots.
export async function fetchRequestCounts(
  token: string,
  from: number,
  to: number,
) {
  const response = await fetch("https://api.cloudflare.com/client/v4/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    signal: AbortSignal.timeout(20_000),
    body: JSON.stringify({
      query: `query Requests($from: Date!, $to: Date!) {
        viewer { zones(filter: {zoneTag: "0f870574c4a4f0ee249260cb93e3bff6"}) {
          httpRequests1dGroups(limit: 8, filter: {
            date_geq: $from, date_lt: $to
          }) { sum { requests } dimensions { date } }
        } }
      }`,
      variables: {
        from: new Date(from).toISOString().slice(0, 10),
        to: new Date(Math.ceil(to / DAY) * DAY).toISOString().slice(0, 10),
      },
    }),
  });
  if (!response.ok)
    throw new Error(`Request analytics HTTP ${response.status}`);
  const result = responseSchema.parse(await response.json());
  if (result.errors?.length || !result.data)
    throw new Error("Request analytics query failed");
  const days = new Map<string, number>();
  for (let day = from; day < to; day += DAY) {
    days.set(new Date(day).toISOString().slice(0, 10), 0);
  }
  for (const row of result.data.viewer.zones[0].httpRequests1dGroups) {
    if (!days.has(row.dimensions.date))
      throw new Error("Unexpected analytics date");
    days.set(row.dimensions.date, row.sum.requests);
  }
  return days;
}
