import type { SVGProps } from "react";

/** SPNI mark: a phone under a magnifying lens, drawn for this app. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <defs>
        <linearGradient id="lg-gold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F8D77A" />
          <stop offset="0.55" stopColor="#E0A82E" />
          <stop offset="1" stopColor="#B07812" />
        </linearGradient>
        <linearGradient id="lg-glass" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3D6FD1" stopOpacity="0.95" />
          <stop offset="1" stopColor="#0B1B3D" stopOpacity="0.95" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="46" height="46" rx="13" fill="url(#lg-gold)" />
      <rect x="1.5" y="1.5" width="45" height="45" rx="12.5" fill="none" stroke="#fff" strokeOpacity="0.35" />
      <rect x="11" y="8" width="17" height="29" rx="4" fill="#0B1B3D" />
      <rect x="13" y="11" width="13" height="21" rx="1.6" fill="#1A3A7A" />
      <path d="M14.5 26 l3 -4 3 2.5 4 -6" stroke="#F2C14E" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="30" cy="27" r="9" fill="url(#lg-glass)" stroke="#0B1B3D" strokeWidth="2.6" />
      <circle cx="27.5" cy="24.5" r="2.6" fill="#fff" fillOpacity="0.55" />
      <path d="M36.5 33.5 L42 39" stroke="#0B1B3D" strokeWidth="4.2" strokeLinecap="round" />
    </svg>
  );
}

/** Generic Android-style robot head (original drawing). */
export function AndroidIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" {...props}>
      <path d="M7.2 4.6 5.9 2.9a.5.5 0 1 1 .8-.6l1.4 1.8A8.6 8.6 0 0 1 12 3.3c1.4 0 2.7.3 3.9.8l1.4-1.8a.5.5 0 1 1 .8.6l-1.3 1.7A7.4 7.4 0 0 1 20.5 11H3.5a7.4 7.4 0 0 1 3.7-6.4ZM8.5 8.4a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm7 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z" />
      <path d="M3.5 12.2h17v6.3a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-6.3Z" opacity=".55" />
    </svg>
  );
}

/** Generic smartphone with a notch, used for iOS. */
export function IphoneIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" {...props}>
      <rect x="6" y="2" width="12" height="20" rx="3" />
      <path d="M10.3 4.6h3.4" strokeWidth="2.4" />
      <path d="M11 19h2" />
    </svg>
  );
}

export function SimChipIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 40 30" {...props}>
      <defs>
        <linearGradient id="chip" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F8DE8A" />
          <stop offset="1" stopColor="#C89220" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="28" rx="6" fill="url(#chip)" stroke="#9C6E10" strokeOpacity=".5" />
      <path d="M1 10h12M1 20h12M27 10h12M27 20h12M13 1v28M27 1v28M13 15h14" stroke="#8A5F0C" strokeOpacity=".55" fill="none" />
    </svg>
  );
}
