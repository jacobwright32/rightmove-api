import { useEffect, useRef, useState } from "react";

/**
 * Returns a ref and a boolean indicating whether the element is visible in the viewport.
 * Once visible, stays true (trigger-once) so the section doesn't unmount on scroll-away.
 */
export function useInView(rootMargin = "200px") {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || inView) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [rootMargin, inView]);

  return { ref, inView };
}
