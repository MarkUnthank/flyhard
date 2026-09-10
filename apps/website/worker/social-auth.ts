import { createRemoteJWKSet, jwtVerify } from "jose";
import type { Env } from "./env";
import { HttpError } from "./http";

const issuer = "https://token.actions.githubusercontent.com";
const keys = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks`));

export async function authorizeSocialPublisher(request: Request, env: Env) {
  const authorization = request.headers.get("Authorization") ?? "";
  // The existing operator credential also permits publishing from a local Mac.
  if (
    env.AUCTION_ADMIN_TOKEN &&
    authorization === `Bearer ${env.AUCTION_ADMIN_TOKEN}`
  )
    return;
  if (!authorization.startsWith("Bearer "))
    throw new HttpError(401, "Publisher authentication required.");
  try {
    const { payload } = await jwtVerify(authorization.slice(7), keys, {
      issuer,
      audience: new URL("/api/social/publish", env.SITE_URL).href,
      algorithms: ["RS256"],
      requiredClaims: ["exp", "iat", "nbf"],
      maxTokenAge: "10 minutes",
    });
    // Pin both immutable repository identity and the specific main-branch job.
    // A fork, PR, other workflow or branch cannot publish production images.
    if (
      payload.repository_id !== "1363155073" ||
      payload.repository_owner_id !== "15160212" ||
      payload.sub !== "repo:MarkUnthank/flyhard:ref:refs/heads/main" ||
      payload.ref !== "refs/heads/main" ||
      payload.workflow_ref !==
        "MarkUnthank/flyhard/.github/workflows/social-images.yml@refs/heads/main" ||
      payload.event_name !== "workflow_dispatch"
    )
      throw new Error("Untrusted publisher");
  } catch {
    throw new HttpError(401, "Publisher authentication failed.");
  }
}
