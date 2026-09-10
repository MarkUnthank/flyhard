import { createRoot } from "react-dom/client";
import CarViewer from "../components/car-viewer";
import { INVENTORY_SIZE, type Placement } from "../lib/auction";
import "@fontsource-variable/dm-sans";
import "./card.css";

declare global {
  interface Window {
    __SOCIAL_PLACEMENTS__: Record<string, Placement>;
  }
}

const square = location.pathname === "/square";
createRoot(document.getElementById("card")!).render(
  <main className={square ? "card square" : "card wide"}>
    <div className="wordmark">
      THE <span>DRIVING</span> FLY
    </div>
    <h1>
      Your brand.
      <br />
      <span>A car.</span>
      {square ? " " : <br />}A fly.
    </h1>
    <div className="car">
      <CarViewer
        placements={window.__SOCIAL_PLACEMENTS__}
        selected={null}
        view="perspective"
        capture
        onSelect={() => {}}
      />
    </div>
    <footer>
      <div>
        {INVENTORY_SIZE} ad spaces. <strong>Outbid a sponsor.</strong>
      </div>
      <span>thedrivingfly.com</span>
    </footer>
  </main>,
);
