import type { SearchState } from "../hooks/usePostcodeSearch";

const messages: Partial<Record<SearchState, string>> = {
  checking: "Checking cache...",
  scraping: "Scraping Rightmove (this may take a while for area searches)...",
  loading: "Loading analytics...",
};

interface Props {
  state: SearchState;
}

export default function LoadingOverlay({ state }: Props) {
  const message = messages[state];
  if (!message) return null;

  return (
    <div className="flex flex-col items-center gap-3 py-12" role="status" aria-live="polite">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-600 border-t-transparent" aria-hidden="true" />
      <p className="text-lg text-gray-600 dark:text-gray-400">{message}</p>
    </div>
  );
}
