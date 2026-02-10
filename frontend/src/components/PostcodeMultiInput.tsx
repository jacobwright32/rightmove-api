import { useEffect, useRef, useState } from "react";
import { suggestPostcodes } from "../api/client";
import { normalisePostcode } from "../utils/formatting";

interface Props {
  postcodes: string[];
  onChange: (postcodes: string[]) => void;
  max?: number;
  disabled?: boolean;
}

export default function PostcodeMultiInput({
  postcodes,
  onChange,
  max = 4,
  disabled,
}: Props) {
  const [input, setInput] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    const clean = normalisePostcode(input);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (clean.length >= 3) {
      debounceRef.current = setTimeout(async () => {
        try {
          const results = await suggestPostcodes(clean);
          const filtered = results.filter((pc) => !postcodes.includes(pc));
          setSuggestions(filtered);
          setShowSuggestions(filtered.length > 0);
        } catch {
          setSuggestions([]);
        }
      }, 400);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, [input, postcodes]);

  function addPostcode(pc: string) {
    const normalised = normalisePostcode(pc);
    if (normalised && !postcodes.includes(normalised) && postcodes.length < max) {
      onChange([...postcodes, normalised]);
    }
    setInput("");
    setSuggestions([]);
    setShowSuggestions(false);
  }

  function removePostcode(pc: string) {
    onChange(postcodes.filter((p) => p !== pc));
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (input.trim()) addPostcode(input.trim());
    }
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 dark:border-gray-600 dark:bg-gray-800">
        {postcodes.map((pc) => (
          <span
            key={pc}
            className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800 dark:bg-blue-900/50 dark:text-blue-300"
          >
            {pc}
            <button
              type="button"
              onClick={() => removePostcode(pc)}
              className="ml-1 text-blue-500 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-200"
              aria-label={`Remove ${pc}`}
            >
              &times;
            </button>
          </span>
        ))}
        {postcodes.length < max && (
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              if (suggestions.length > 0) setShowSuggestions(true);
            }}
            placeholder={postcodes.length === 0 ? "Type a postcode..." : "Add another..."}
            disabled={disabled}
            className="min-w-[120px] flex-1 bg-transparent py-1 text-sm text-gray-900 placeholder-gray-400 focus:outline-none disabled:opacity-50 dark:text-gray-100 dark:placeholder-gray-500"
            aria-label="Add postcode"
          />
        )}
      </div>

      {showSuggestions && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-48 overflow-y-auto dark:border-gray-600 dark:bg-gray-800">
          {suggestions.map((pc) => (
            <button
              key={pc}
              type="button"
              onClick={() => addPostcode(pc)}
              className="w-full px-4 py-2 text-left text-sm hover:bg-blue-50 focus:bg-blue-50 focus:outline-none dark:text-gray-300 dark:hover:bg-gray-700 dark:focus:bg-gray-700"
            >
              {pc}
            </button>
          ))}
        </div>
      )}

      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
        Add {max - postcodes.length} more postcode{max - postcodes.length !== 1 ? "s" : ""} (max {max})
      </p>
    </div>
  );
}
