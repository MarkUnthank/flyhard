import { minimumBid, money } from "../src/lib/auction";

export function checkoutEmail(session: {
  customer_details?: { email?: string | null } | null;
  customer_email?: string | null;
}): string | null {
  const email = session.customer_details?.email || session.customer_email;
  return email &&
    email.length <= 254 &&
    /^[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+$/.test(email)
    ? email.trim()
    : null;
}

const escapeHtml = (value: string) =>
  value.replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ]!,
  );

export function outbidEmail(input: {
  siteUrl: string;
  slotId: string;
  slotName: string;
  brand: string;
  previousAmount: number;
  replacementAmount: number;
  currentAmount: number;
  test: boolean;
}): Pick<EmailMessageBuilder, "subject" | "html" | "text"> {
  const url = new URL("/", input.siteUrl);
  url.searchParams.set("spot", input.slotId);
  const subject = `${input.test ? "[TEST] " : ""}You’ve been outbid — The Driving Fly`;
  const intro = `Your ${money(input.previousAmount)} placement for ${input.brand} on ${input.slotName} was replaced by a confirmed ${money(input.replacementAmount)} bid.`;
  const price = `The next bid starts at ${money(minimumBid(input.currentAmount))} USD. The auction stays live, so check the latest price before paying.`;
  const test = input.test
    ? "TEST NOTIFICATION — This is a sandbox auction. No live ad was replaced and no real payment was made."
    : "";
  const footer =
    "You’re receiving this update because this email was used at Stripe checkout for this placement. Your email address is never shown on the site. Your past support stays in the recent supporter history. Thank you for riding with us.";
  return {
    subject,
    text: [
      test,
      "Your spot has a new passenger.",
      intro,
      price,
      `View your spot and bid again: ${url.href}`,
      footer,
    ]
      .filter(Boolean)
      .join("\n\n"),
    html: `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f5f6f1;color:#273223;font-family:Arial,Helvetica,sans-serif"><table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:40px 16px"><table role="presentation" width="560" cellspacing="0" cellpadding="0" style="width:100%;max-width:560px;background:#fff;border:1px solid #dfe4d9;border-radius:16px"><tr><td style="padding:36px"><p style="margin:0 0 32px;font-size:20px;font-weight:bold">The Driving Fly.</p>${test ? `<p style="padding:12px;background:#fff2c9;font-size:14px;line-height:1.5">${escapeHtml(test)}</p>` : ""}<p style="font-size:12px;letter-spacing:2px;color:#56654e">LIVE AUCTION UPDATE</p><h1 style="font-size:32px;line-height:1.15;letter-spacing:-1px;margin:12px 0 24px">Your spot has a<br>new passenger.</h1><p style="font-size:17px;line-height:1.6">${escapeHtml(intro)}</p><p style="font-size:16px;line-height:1.6">${escapeHtml(price)}</p><p style="margin:30px 0"><a href="${escapeHtml(url.href)}" style="display:inline-block;background:#d9f26e;color:#243019;text-decoration:none;font-size:16px;font-weight:bold;padding:16px 24px;border-radius:6px">View your spot &amp; bid again →</a></p><p style="font-size:13px;line-height:1.6;color:#56654e">${escapeHtml(footer)}</p><p style="margin-top:28px;font-size:13px;color:#56654e">A <a href="https://reallynice.company" style="color:#56654e">Really Nice</a> project.</p></td></tr></table></td></tr></table></body></html>`,
  };
}

// Do not persist or log provider messages: they can contain email addresses.
export function emailErrorCode(error: unknown): string {
  const code =
    typeof error === "object" && error !== null && "code" in error
      ? String(error.code)
      : "";
  return /^E_[A-Z_]{1,60}$/.test(code) ? code : "E_NOTIFICATION_RETRY";
}
