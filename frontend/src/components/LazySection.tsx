import type { ReactNode } from "react";
import { useInView } from "../hooks/useInView";

interface Props {
  children: ReactNode;
  /** Minimum height placeholder before the section loads */
  minHeight?: string;
}

/**
 * Defers rendering of children until the section scrolls near the viewport.
 * Prevents external API calls from firing on page load for below-fold sections.
 */
export default function LazySection({ children, minHeight = "80px" }: Props) {
  const { ref, inView } = useInView("300px");

  return (
    <div ref={ref} style={{ minHeight: inView ? undefined : minHeight }}>
      {inView ? children : null}
    </div>
  );
}
