"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

function Spinner() {
  return (
    <span className="relative flex h-12 w-12 items-center justify-center">
      <span className="absolute inset-0 rounded-full border-2 border-purple-500/20" />
      <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-purple-500" />
      <span className="h-2 w-2 rounded-full bg-purple-400/80" />
    </span>
  );
}

/** Full-page loader used by the root route segment. */
export function GlobalLoading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-[#0a0a0f]">
      <div className="flex flex-col items-center gap-4">
        <Spinner />
        <p className="text-sm text-gray-400">{label}</p>
      </div>
    </div>
  );
}

/** In-layout loader used while an app or system-owner route is loading. */
export function SectionLoading({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Spinner />
        <p className="text-sm text-gray-400">{label}</p>
      </div>
    </div>
  );
}

/**
 * Immediate feedback for client-side navigation. App Router does not expose
 * router events, so we listen for internal link clicks and keep a slim top
 * progress bar visible until the pathname changes.
 */
export function GlobalRouteProgress() {
  const pathname = usePathname();
  const [active, setActive] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  };

  useEffect(() => {
    setActive(false);
    clearTimer();
    return clearTimer;
  }, [pathname]);

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }

      const anchor = (event.target as HTMLElement | null)?.closest("a");
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (
        !href ||
        href.startsWith("#") ||
        href.startsWith("http") ||
        href.startsWith("mailto:") ||
        href.startsWith("tel:") ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download")
      ) {
        return;
      }

      const target = new URL(anchor.href, window.location.href);
      if (target.pathname === pathname) return;

      setActive(true);
      clearTimer();
      // Safety net: never leave the bar stuck if navigation is blocked.
      timeoutRef.current = setTimeout(() => setActive(false), 15000);
    };

    document.addEventListener("click", handleClick, true);
    return () => {
      document.removeEventListener("click", handleClick, true);
      clearTimer();
    };
  }, [pathname]);

  if (!active) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-0 z-[150] h-0.5 overflow-hidden bg-purple-500/15"
      role="progressbar"
      aria-label="Loading page"
    >
      <span className="route-progress-bar" />
    </div>
  );
}
