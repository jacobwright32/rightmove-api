import { NavLink } from "react-router-dom";
import ThemeToggle from "./ThemeToggle";

const links = [
  { to: "/", label: "Search" },
  { to: "/market", label: "Market Overview" },
  { to: "/compare", label: "Compare Areas" },
  { to: "/insights", label: "Housing Insights" },
  { to: "/map", label: "Map" },
];

export default function NavBar() {
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
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
}
