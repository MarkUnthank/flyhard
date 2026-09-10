export default function FlyMark({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
    >
      <g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
        <path
          d="M17 15C5-3 0 15 14 21M23 15C35-3 40 15 26 21"
          fill="currentColor"
          fillOpacity=".06"
        />
        <path d="m15 21-8-1m9 5-8 5m10-2-3 8m10-15 8-1m-9 5 8 5m-10-2 3 8" />
        <ellipse cx="20" cy="24" rx="5" ry="9" fill="currentColor" />
        <circle cx="17" cy="13" r="4" fill="currentColor" />
        <circle cx="23" cy="13" r="4" fill="currentColor" />
        <path d="m17 9-2-4m8 4 2-4" />
      </g>
    </svg>
  );
}
