import Link from "next/link";
import FlyMark from "@/components/fly-mark";
export default function Credits() {
  return (
    <main className="legal-page">
      <Link href="/" className="wordmark">
        <FlyMark />
        The Driving Fly.
      </Link>
      <h1>Credits</h1>
      <h2>The Mini</h2>
      <p>
        Vehicle geometry and original textures come from CARLA 0.9.16, Computer
        Vision Center (CVC), Universitat Autònoma de Barcelona. Blueprint:
        vehicle.mini.cooper_s_2021. CARLA identifies its specific assets as CC
        BY. The advertising layout, web preparation, and reconstructed Blender
        materials are modifications for Mark Unthank’s The Driving Fly project.
      </p>
      <p>
        <a href="https://github.com/carla-simulator/carla/tree/0.9.16#licenses">
          CARLA licensing and attribution
        </a>
      </p>
      <h2>Lettering and software</h2>
      <p>
        Model lettering uses Barlow Condensed under the SIL Open Font License.
        The site uses Next.js, OpenNext for Cloudflare, Three.js, and Lucide
        icons.{" "}
        <a href="/model/BarlowCondensed-OFL.txt">Read the Barlow license</a>.
      </p>
      <h2>Design inspiration</h2>
      <p>
        The clean auction layout was inspired by{" "}
        <a href="https://brandmymac.com/">Brand My Mac</a>. The continuously
        replaceable placement mechanic was inspired by{" "}
        <a href="https://outbid.lol/">outbid.lol</a>.
      </p>
      <p>
        The Driving Fly is not affiliated with or endorsed by MINI, BMW, or
        these reference projects.
      </p>
      <p>
        <Link href="/">← Back to the car</Link>
      </p>
    </main>
  );
}
