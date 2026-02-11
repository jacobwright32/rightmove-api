import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar";
import CompareAreasPage from "./pages/CompareAreasPage";
import HousingInsightsPage from "./pages/HousingInsightsPage";
import MarketOverviewPage from "./pages/MarketOverviewPage";
import PropertyDetailPage from "./pages/PropertyDetailPage";
import SearchPage from "./pages/SearchPage";

const MapViewPage = lazy(() => import("./pages/MapViewPage"));
const ModellingPage = lazy(() => import("./pages/ModellingPage"));

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
        <NavBar />
        <Suspense fallback={<div className="flex items-center justify-center py-20 text-gray-500">Loading...</div>}>
          <Routes>
            <Route path="/" element={<SearchPage />} />
            <Route path="/market" element={<MarketOverviewPage />} />
            <Route path="/compare" element={<CompareAreasPage />} />
            <Route path="/insights" element={<HousingInsightsPage />} />
            <Route path="/map" element={<MapViewPage />} />
            <Route path="/model" element={<ModellingPage />} />
            <Route path="/property/:id" element={<PropertyDetailPage />} />
          </Routes>
        </Suspense>
      </div>
    </BrowserRouter>
  );
}
