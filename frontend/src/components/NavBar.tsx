import { useState } from "react";
import { NavLink } from "react-router-dom";
import { resetDatabase } from "../api/client";
import ThemeToggle from "./ThemeToggle";

const links = [
  { to: "/", label: "Search" },
  { to: "/market", label: "Market Overview" },
  { to: "/compare", label: "Compare Areas" },
  { to: "/insights", label: "Housing Insights" },
  { to: "/map", label: "Map" },
  { to: "/model", label: "Model" },
  { to: "/enrich", label: "Enrich" },
];

export default function NavBar() {
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);

  const handleReset = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setResetting(true);
    try {
      await resetDatabase();
      window.location.href = "/";
    } catch {
      setResetting(false);
      setConfirming(false);
    }
  };

  return (
    <nav className="bg-white shadow-sm dark:bg-gray-800 dark:shadow-gray-900/50">
      <div className="mx-auto max-w-6xl px-4">
        <div className="flex h-14 items-center justify-between">
          <div className="flex items-center gap-1">
            <span className="mr-4 text-lg font-bold text-gray-900 dark:text-gray-100">
              Rightmove
            </span>
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.to === "/"}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-blue-50 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </div>
          <div className="flex items-center gap-2">
            {confirming && (
              <button
                onClick={() => setConfirming(false)}
                className="rounded-md px-2 py-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleReset}
              disabled={resetting}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                confirming
                  ? "bg-red-600 text-white hover:bg-red-700"
                  : "border border-red-300 text-red-600 hover:bg-red-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
              } disabled:opacity-50`}
            >
              {resetting
                ? "Resetting..."
                : confirming
                  ? "Confirm Reset"
                  : "Reset DB"}
            </button>
            <ThemeToggle />
          </div>
        </div>
      </div>
    </nav>
  );
}
