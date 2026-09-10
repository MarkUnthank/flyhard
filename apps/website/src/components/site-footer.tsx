import FlyMark from "./fly-mark";

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div>
        <a className="wordmark" href="/">
          <FlyMark size={25} />
          <span>The Driving Fly.</span>
        </a>
        <p className="company-credit">
          A{" "}
          <a
            href="https://reallynice.company"
            target="_blank"
            rel="noopener noreferrer"
          >
            Really Nice
          </a>{" "}
          project.
        </p>
      </div>
      <div className="footer-links">
        <a href="/media">Videos &amp; data</a>
        <a
          className="footer-social"
          href="https://x.com/alright_mark"
          target="_blank"
          rel="noopener noreferrer"
          aria-label="@alright_mark on X"
        >
          <svg
            viewBox="0 0 24 24"
            width="14"
            height="14"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.64 7.584H.47l8.6-9.835L0 1.154h7.594l5.243 6.932 6.064-6.933Zm-1.29 19.49h2.039L6.487 3.24H4.3l13.31 17.403Z" />
          </svg>
          @alright_mark
        </a>
        <a href="/terms">Placement terms</a>
        <a href="/privacy">Privacy</a>
        <a href="/credits">Credits</a>
      </div>
      <p className="footer-disclaimer">
        Vehicle model adapted from CARLA 0.9.16 (CVC, Universitat Autònoma de
        Barcelona), CC BY. The Driving Fly is an independent project.
      </p>
    </footer>
  );
}
