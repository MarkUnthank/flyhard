import Link from "next/link";
import FlyMark from "@/components/fly-mark";
export default function Privacy() {
  return (
    <main className="legal-page">
      <Link href="/" className="wordmark">
        <FlyMark />
        The Driving Fly.
      </Link>
      <h1>Privacy</h1>
      <p>
        The Driving Fly is operated by Mark Unthank. We use information you
        provide to deliver your advertising placement and manage the live
        auction.
      </p>
      <h2>What becomes public</h2>
      <p>
        Your submitted brand name, message, website, artwork, winning bid, and
        publication time are public when your placement goes live. These details
        may remain in recent supporter history after you are outbid. Do not
        upload private information as artwork.
      </p>
      <h2>Payments</h2>
      <p>
        Stripe collects and processes your payment and billing details through
        its hosted checkout. This website does not receive or store your full
        card number. We retain checkout and payment identifiers, bid amounts,
        artwork references, and payment status to verify purchases, prevent
        duplicates, and handle refunds.
      </p>
      <h2>Outbid notifications</h2>
      <p>
        We use the email address from your confirmed Stripe checkout to tell you
        when another paid bid replaces your placement. We store it privately
        with your purchase and send these transactional updates through
        Cloudflare Email Service. Your address is never included in public
        auction data or shared with other bidders. This does not subscribe you
        to marketing emails.
      </p>
      <h2>Custom wrap purchases</h2>
      <p>
        For a custom wrap, we privately retain the brand name and email address
        from Stripe Checkout, the purchase amount and order number, and payment
        and notification status. After payment is confirmed, we use Cloudflare
        Email Service to email you a meeting link and design files, and to
        notify the project operator of your purchase. These are transactional
        emails and do not subscribe you to marketing. Buyer contact details and
        payment identifiers are never included in the public offer or auction
        data. The wrap price, purchase count, and total funding are public.
      </p>
      <h2>Hosting and connection data</h2>
      <p>
        Cloudflare hosts the site, artwork, and auction state. Short-lived
        IP-based request counters help prevent abuse; the application expires
        them after two minutes. Hosting providers may retain operational logs
        under their own policies. The online counter counts active browser
        connections, not identifiable people. We do not add advertising trackers
        or analytics cookies.
      </p>
      <h2>Retention and requests</h2>
      <p>
        Unused uploads are removed after 24 hours. Paid placement and
        transaction records are retained to maintain the auction and meet
        accounting obligations. To ask about access, correction, or deletion,
        use the merchant contact details on your payment receipt. Public
        information and records needed for accounting, fraud prevention, or a
        legal obligation may need to be retained.
      </p>
      <p>
        See <a href="https://stripe.com/privacy">Stripe’s privacy policy</a> and{" "}
        <a href="https://www.cloudflare.com/privacypolicy/">
          Cloudflare’s privacy policy
        </a>
        .
      </p>
      <p>
        <Link href="/">← Back to the car</Link>
      </p>
    </main>
  );
}
