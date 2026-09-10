import Link from "next/link";
import FlyMark from "@/components/fly-mark";
export default function Terms() {
  return (
    <main className="legal-page">
      <Link href="/" className="wordmark">
        <FlyMark />
        The Driving Fly.
      </Link>
      <h1>Advertising terms</h1>
      <p>
        The Driving Fly is an independent project by Mark Unthank. Buying a spot
        supports the experiment and displays your artwork on a chosen surface of
        the interactive Mini on this website.
      </p>
      <h2 id="custom-wrap">Full custom wrap and two videos</h2>
      <p>
        The custom wrap package includes a full custom livery designed for your
        brand on our simulated Mini, and two released project videos featuring
        that wrap. This is a digital project vehicle, not a physical car wrap.
        After payment, we email your checkout address with a meeting link and
        the car’s paint texture. Book a meeting with Mark to discuss your brief
        and artwork and start making your wrap. Projects enter production in
        purchase order; payment does not instantly replace the website’s live
        auction placements.
      </p>
      <p>
        The first package costs US $10,000. After each confirmed purchase, the
        next package becomes available immediately for US $1 more, even while
        earlier projects are in production. You pay the full displayed amount
        once, immediately through Stripe Checkout. There is no subscription or
        later balance. Opening checkout does not reserve that price. If someone
        else purchases it first, your competing payment is refunded in full;
        bank processing times vary. We never charge a higher price without a new
        checkout.
      </p>
      <p>
        The package promises two project videos featuring your wrap, with no
        guaranteed audience, views, clicks, or financial return. The artwork
        rules below also apply to custom wraps. Contact us using your Stripe
        receipt for production or payment questions. Nothing in these terms
        limits your rights under applicable consumer law.
      </p>
      <h2>The live auction</h2>
      <p>
        Every unclaimed spot starts at US $1. A replacement must pay at least US
        $1 more than the current confirmed bid. Your payment is the full amount
        of your new bid, not the difference. There is no closing date. Browsing
        or opening checkout does not reserve a spot.
      </p>
      <h2>When your placement starts and ends</h2>
      <p>
        Choose your bid and pay first, then return to add your brand, website,
        and artwork. Your artwork goes live when you publish those details and
        the server has verified successful payment. Until then, the current ad
        remains live and bidding continues. You can return using your private
        completion link or this browser to finish your paid spot. Your ad stays
        until a higher paid bid publishes its artwork. There is no guaranteed
        minimum display time, audience, number of impressions, clicks, or
        appearance in project videos. Previous advertisers may remain in public
        supporter history.
      </p>
      <h2>Simultaneous purchases and refunds</h2>
      <p>
        If your payment is already beaten before your artwork is published, we
        request a full refund automatically. Bank processing times vary. If your
        artwork was published and later outbid, the completed placement is not
        refunded simply because another person paid more. This does not limit
        any rights you have under applicable consumer law.
      </p>
      <h2>Your artwork and website</h2>
      <p>
        You must have the right to use the artwork, name, message, and
        destination website you submit. You give The Driving Fly permission to
        display that artwork, name, and message in your placement, supporter
        history, and depictions of the project’s livery. Do not submit illegal,
        hateful, sexually explicit, deceptive, harmful, or infringing content.
        We may remove content that breaks these terms or a legal requirement. A
        removal does not entitle you to a replacement placement.
      </p>
      <h2>Payment and the experiment</h2>
      <p>
        Stripe processes card payments. The checkout shows your total before you
        pay. Funding supports an ongoing research experiment; purchasing a
        placement does not buy ownership, a financial return, or a promise that
        the fly will achieve autonomous driving.
      </p>
      <h2>Questions or problems</h2>
      <p>
        Keep your Stripe receipt. For a payment issue, use the merchant contact
        details on that receipt so we can identify the payment and help.
      </p>
      <p>
        <Link href="/">← Back to the car</Link>
      </p>
    </main>
  );
}
