import { BrowserRouter, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import CompareAreasPage from "./pages/CompareAreasPage";
import MarketOverviewPage from "./pages/MarketOverviewPage";
import PropertyDetailPage from "./pages/PropertyDetailPage";
import SearchPage from "./pages/SearchPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <NavBar />
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/market" element={<MarketOverviewPage />} />
          <Route path="/compare" element={<CompareAreasPage />} />
          <Route path="/property/:id" element={<PropertyDetailPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
