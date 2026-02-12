import { useCallback, useRef, useState } from "react";
import {
  getAnalytics,
  getProperties,
  scrapeArea,
  scrapePostcode,
} from "../api/client";
import type { PostcodeAnalytics, PropertyDetail } from "../api/types";

export type SearchState =
  | "idle"
  | "checking"
  | "scraping"
  | "loading"
  | "done"
  | "error";

export interface ScrapeOptions {
  pages: number;
  linkCount: number;
  maxPostcodes: number;
  floorplan: boolean;
  extraFeatures: boolean;
  saveParquet: boolean;
  force: boolean;
}

export interface SearchResult {
  analytics: PostcodeAnalytics | null;
  properties: PropertyDetail[];
}

const FULL_POSTCODE_RE = /^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$/;

export function usePostcodeSearch() {
  const [state, setState] = useState<SearchState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResult>({
    analytics: null,
    properties: [],
  });
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const search = useCallback(async (postcode: string, opts: ScrapeOptions) => {
    // Cancel any in-flight request
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setError(null);
    setScrapeMessage(null);
    const clean = postcode.toUpperCase().replace(/[\s-]/g, "");
    const isFullPostcode = FULL_POSTCODE_RE.test(clean);

    try {
      setState("scraping");

      // Map UI linkCount: 0=Off (fast), -1=All (detail, no limit), N=detail N pages
      const apiLinkCount =
        opts.linkCount === 0 ? undefined : opts.linkCount === -1 ? 0 : opts.linkCount;

      if (isFullPostcode) {
        // Single postcode scrape
        const result = await scrapePostcode(clean, {
          pages: opts.pages,
          linkCount: apiLinkCount,
          floorplan: opts.floorplan,
          extraFeatures: opts.extraFeatures,
          saveParquet: opts.saveParquet,
          force: opts.force,
        });
        if (result.skipped) {
          setScrapeMessage(result.message);
        }
      } else {
        // Area scrape — discover postcodes and scrape each
        const areaResult = await scrapeArea(clean, {
          pages: opts.pages,
          linkCount: apiLinkCount,
          maxPostcodes: opts.maxPostcodes,
          floorplan: opts.floorplan,
          extraFeatures: opts.extraFeatures,
          saveParquet: opts.saveParquet,
          force: opts.force,
        });
        setScrapeMessage(areaResult.message);
      }

      // Check if cancelled before continuing
      if (controller.signal.aborted) return;

      setState("loading");
      if (controller.signal.aborted) return;

      const [analytics, properties] = await Promise.allSettled([
        getAnalytics(clean),
        getProperties(clean),
      ]);

      // Check after await — if aborted during fetch, discard stale results
      if (controller.signal.aborted) return;

      setResult({
        analytics: analytics.status === "fulfilled" ? analytics.value : null,
        properties: properties.status === "fulfilled" ? properties.value : [],
      });
      setState("done");
    } catch (err: unknown) {
      // Don't set error state if this was an intentional cancellation
      if (controller.signal.aborted) return;

      const message =
        err instanceof Error ? err.message : "An unexpected error occurred";
      setError(message);
      setState("error");
    }
  }, []);

  return { state, error, result, search, scrapeMessage };
}
