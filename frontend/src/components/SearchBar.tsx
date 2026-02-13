import { useEffect, useRef, useState } from "react";
import { suggestPostcodes } from "../api/client";
import type { ScrapeOptions } from "../hooks/usePostcodeSearch";
import { normalisePostcode } from "../utils/formatting";

interface Props {
  onSearch: (postcode: string, opts: ScrapeOptions) => void;
  disabled?: boolean;
}

const UK_POSTCODE_RE = /^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$/;

export default function SearchBar({ onSearch, disabled }: Props) {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"house_prices" | "for_sale">("house_prices");
  const [pages, setPages] = useState(1);
  const [linkCount, setLinkCount] = useState(0);
  const [maxPostcodes, setMaxPostcodes] = useState(0);
  const [floorplan, setFloorplan] = useState(false);
  const [extraFeatures, setExtraFeatures] = useState(false);
  const [saveParquet, setSaveParquet] = useState(false);
  const [force, setForce] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Fetch suggestions when input is a partial postcode (3+ chars, not a full postcode)
  useEffect(() => {
    const clean = normalisePostcode(input);
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (clean.length >= 3 && !UK_POSTCODE_RE.test(clean)) {
      debounceRef.current = setTimeout(async () => {
        setLoadingSuggestions(true);
        try {
          const results = await suggestPostcodes(clean);
          setSuggestions(results);
          setShowSuggestions(results.length > 0);
        } catch {
          setSuggestions([]);
        } finally {
          setLoadingSuggestions(false);
        }
      }, 400);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, [input]);

  function selectPostcode(postcode: string) {
    setInput(postcode);
    setShowSuggestions(false);
    setSuggestions([]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const normalised = normalisePostcode(input);
    if (normalised.length < 3) {
      setValidationError("Enter at least 3 characters (e.g. SW20 or SW20 8NY)");
      return;
    }
    setValidationError(null);
    setShowSuggestions(false);
    onSearch(normalised, { pages, linkCount, maxPostcodes, floorplan, extraFeatures, saveParquet, force, mode });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col items-center gap-3">
      {/* Mode toggle */}
      <div className="flex rounded-lg border border-gray-300 overflow-hidden dark:border-gray-600">
        <button
          type="button"
          onClick={() => setMode("house_prices")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            mode === "house_prices"
              ? "bg-blue-600 text-white"
              : "bg-white text-gray-700 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          }`}
        >
          House Prices
        </button>
        <button
          type="button"
          onClick={() => setMode("for_sale")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            mode === "for_sale"
              ? "bg-blue-600 text-white"
              : "bg-white text-gray-700 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
          }`}
        >
          Current Listings
        </button>
      </div>

      <div className="flex gap-2" ref={wrapperRef}>
        <div className="relative">
          <input
            type="text"
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              setValidationError(null);
            }}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggestions(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") setShowSuggestions(false);
            }}
            placeholder="Enter postcode (e.g. E1W 1AT)"
            aria-label="Enter UK postcode"
            disabled={disabled}
            className="rounded-lg border border-gray-300 px-4 py-3 text-lg w-full md:w-72 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500"
          />

          {/* Suggestions dropdown */}
          {showSuggestions && (
            <div className="absolute z-10 mt-1 w-72 rounded-lg border border-gray-200 bg-white shadow-lg max-h-60 overflow-y-auto dark:border-gray-600 dark:bg-gray-800">
              {loadingSuggestions && (
                <div className="px-4 py-2 text-sm text-gray-400">
                  Searching postcodes...
                </div>
              )}
              {suggestions.map((pc) => (
                <button
                  key={pc}
                  type="button"
                  onClick={() => selectPostcode(pc)}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-blue-50 focus:bg-blue-50 focus:outline-none dark:text-gray-300 dark:hover:bg-gray-700 dark:focus:bg-gray-700"
                >
                  {pc}
                </button>
              ))}
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="rounded-lg bg-blue-600 px-6 py-3 text-lg font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Search
        </button>
      </div>

      {/* Scrape options */}
      <div className="flex items-center gap-6 text-sm text-gray-600 dark:text-gray-400 flex-wrap justify-center">
        <label className="flex items-center gap-2">
          Pages
          <input
            type="number"
            min={1}
            max={50}
            value={pages}
            onChange={(e) => setPages(Math.max(1, Number(e.target.value)))}
            disabled={disabled}
            className="w-16 rounded border border-gray-300 px-2 py-1 text-center focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300"
          />
        </label>
        {mode === "house_prices" && (
          <label className="flex items-center gap-2">
            Detail links
            <select
              value={linkCount}
              onChange={(e) => setLinkCount(Number(e.target.value))}
              disabled={disabled}
              className="rounded border border-gray-300 px-2 py-1 text-center focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300"
            >
              <option value={0}>Off</option>
              <option value={5}>5</option>
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={-1}>All</option>
            </select>
          </label>
        )}
        <label className="flex items-center gap-2">
          Max postcodes
          <select
            value={maxPostcodes}
            onChange={(e) => setMaxPostcodes(Number(e.target.value))}
            disabled={disabled}
            className="rounded border border-gray-300 px-2 py-1 text-center focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300"
          >
            <option value={0}>All</option>
            <option value={5}>5</option>
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </label>
        {mode === "house_prices" && (
          <>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={floorplan}
                onChange={(e) => setFloorplan(e.target.checked)}
                disabled={disabled}
                className="rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600"
              />
              Floorplans
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={extraFeatures}
                onChange={(e) => setExtraFeatures(e.target.checked)}
                disabled={disabled}
                className="rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600"
              />
              Key features
            </label>
          </>
        )}
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={saveParquet}
            onChange={(e) => setSaveParquet(e.target.checked)}
            disabled={disabled}
            className="rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600"
          />
          Save as you go
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
            disabled={disabled}
            className="rounded border-gray-300 focus:ring-blue-500 disabled:opacity-50 dark:border-gray-600"
          />
          Re-scrape existing
        </label>
        {mode === "house_prices" && (
          <span className="text-xs text-gray-400">Off = fast mode</span>
        )}
      </div>

      {validationError && (
        <p className="text-red-500 text-sm">{validationError}</p>
      )}
    </form>
  );
}
