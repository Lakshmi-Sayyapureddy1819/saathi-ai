/** Saathi Care mark: a heart (care) with a pulse line running through it (a companion who is always with you). Original artwork. */
export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="Saathi Care" focusable="false">
      <defs>
        <linearGradient id="lg-bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#7c83ff" /><stop offset="0.55" stopColor="#5a4fe0" /><stop offset="1" stopColor="#a855f7" /></linearGradient>
        <linearGradient id="lg-heart" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffffff" /><stop offset="1" stopColor="#e0e4ff" /></linearGradient>
      </defs>
      <rect width="40" height="40" rx="12" fill="url(#lg-bg)" />
      <path d="M0 0h40v20C30 14 16 16 0 8z" fill="#fff" fillOpacity=".12" />
      <path className="logo-heart" d="M20 31.5C9 24 7.800 15.800 12.800 12.600c3.300-2.100 6.200-.2 7.200 2 1-2.200 3.900-4.100 7.200-2 5 3.200 3.800 11.400-7.200 18.900z" fill="url(#lg-heart)" />
      <path className="logo-pulse" d="M9.500 20.500h5l2.300-4.800 3.400 9.600 2.600-6.400 1.200 1.600h6.500" fill="none" stroke="#4a3fd0" strokeWidth="2.100" strokeLinecap="round" strokeLinejoin="round" pathLength="100" />
    </svg>
  );
}

export function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <a className="brand" href="#/" aria-label="Saathi Care home">
      <LogoMark />
      {!collapsed && <span className="brand-text"><b>Saathi</b> Care</span>}
    </a>
  );
}
