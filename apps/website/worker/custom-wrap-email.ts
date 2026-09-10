import { money } from "../src/lib/auction";
import { WRAP_VIDEOS } from "../src/lib/custom-wrap";

export const WRAP_BOOKING_URL = "https://cal.com/mark-unthank/meeting";
export const WRAP_TEXTURE_URL =
  "https://github.com/MarkUnthank/flyhard/blob/main/apps/mini-livery/custom-wrap/M_Bodywork_Mini2021_d.png";
export const WRAP_DESIGN_FILES_URL =
  "https://github.com/MarkUnthank/flyhard/tree/main/apps/mini-livery/custom-wrap";

export function buyerWrapEmail(input: {
  amount: number;
  orderNumber: number;
  test: boolean;
}): Pick<EmailMessageBuilder, "subject" | "text" | "html"> {
  const subject = `${input.test ? "[TEST] " : ""}Your custom wrap is booked — let’s make it yours`;
  const test = input.test
    ? "TEST PURCHASE — no real money was charged. Do not book a meeting or begin production for this test."
    : "";
  const confirmation = `Custom wrap #${input.orderNumber} is paid in full: ${money(input.amount)} USD. Your package includes one full custom wrap for the simulated Mini and ${WRAP_VIDEOS} released project videos featuring it.`;
  const meeting =
    "Book a meeting with me ASAP so we can get your brief together and make your wrap.";
  const design =
    "In the meantime, feel free to vibe, sketch, or start designing your wrap. Grab the car’s paint texture on GitHub below and bring any ideas, logos, colours, or references to our call. You don’t need a finished design — we’ll make it together.";
  return {
    subject,
    text: [
      test,
      "You’re in. Let’s make this car yours.",
      confirmation,
      meeting,
      `Book a meeting: ${WRAP_BOOKING_URL}`,
      design,
      `Paint texture on GitHub: ${WRAP_TEXTURE_URL}`,
      `Design files and tips: ${WRAP_DESIGN_FILES_URL}`,
      "See you soon,\nMark\nThe Driving Fly",
    ]
      .filter(Boolean)
      .join("\n\n"),
    html: `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f5f6f1;color:#273223;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:40px 16px">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="width:100%;max-width:560px;background:#fff;border:1px solid #dfe4d9;border-radius:16px"><tr><td style="padding:36px">
<p style="margin:0 0 32px;font-size:20px;font-weight:bold">The Driving Fly.</p>
${test ? `<p style="padding:12px;background:#fff2c9;font-size:14px;line-height:1.5">${test}</p>` : ""}
<p style="font-size:12px;letter-spacing:2px;color:#56654e">YOUR CUSTOM WRAP · #${input.orderNumber}</p>
<h1 style="font-size:32px;line-height:1.15;letter-spacing:-1px;margin:12px 0 24px">You’re in.<br>Let’s make this car yours.</h1>
<p style="font-size:16px;line-height:1.6">${confirmation}</p>
<p style="font-size:17px;line-height:1.6">${meeting}</p>
<p style="margin:30px 0"><a href="${WRAP_BOOKING_URL}" style="display:inline-block;background:#d9f26e;color:#243019;text-decoration:none;font-size:16px;font-weight:bold;padding:16px 24px;border-radius:6px">Book a meeting with Mark →</a></p>
<p style="font-size:16px;line-height:1.6">${design}</p>
<p style="font-size:16px;line-height:1.8"><a href="${WRAP_TEXTURE_URL}" style="color:#354b19">Get the paint texture on GitHub →</a><br><a href="${WRAP_DESIGN_FILES_URL}" style="color:#354b19">Design files and tips →</a></p>
<p style="margin-top:32px;font-size:16px;line-height:1.6">See you soon,<br><strong>Mark</strong></p>
</td></tr></table></td></tr></table></body></html>`,
  };
}
