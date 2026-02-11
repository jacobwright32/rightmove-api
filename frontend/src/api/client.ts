import axios from "axios";
import type {
  AreaScrapeResponse,
  AvailableFeaturesResponse,
  CrimeSummaryResponse,
  EPCEnrichmentResponse,
  FloodRiskResponse,
  GrowthLeaderboardEntry,
  PropertyGeoPoint,
  HousingInsightsFilters,
  HousingInsightsResponse,
  MarketOverview,
  PlanningResponse,
  PostcodeAnalytics,
  PostcodeGrowthResponse,
  PostcodePredictionResponse,
  PostcodeStatus,
  PropertyBrief,
  PropertyDetail,
  PropertyListingResponse,
  ScrapeResponse,
  SinglePredictionResponse,
  TrainRequest,
  TrainResponse,
  TransportEnrichmentResponse,
} from "./types";

const api = axios.create({ baseURL: "/api/v1" });

export async function checkPostcodeStatus(
  postcode: string
): Promise<PostcodeStatus> {
  const res = await api.get<PostcodeStatus>(
    `/properties/postcode/${encodeURIComponent(postcode)}/status`
  );
  return res.data;
}

export async function scrapePostcode(
  postcode: string,
  opts?: { pages?: number; linkCount?: number; floorplan?: boolean; extraFeatures?: boolean; saveParquet?: boolean; skipExisting?: boolean; force?: boolean }
): Promise<ScrapeResponse> {
  const params: Record<string, number | boolean> = {};
  if (opts?.pages) params.pages = opts.pages;
  if (opts?.linkCount !== undefined) params.link_count = opts.linkCount;
  if (opts?.floorplan) params.floorplan = true;
  if (opts?.extraFeatures) params.extra_features = true;
  if (opts?.saveParquet) params.save_parquet = true;
  if (opts?.skipExisting === false) params.skip_existing = false;
  if (opts?.force) params.force = true;
  const res = await api.post<ScrapeResponse>(
    `/scrape/postcode/${encodeURIComponent(postcode)}`,
    null,
    { params }
  );
  return res.data;
}

export async function getAnalytics(
  postcode: string
): Promise<PostcodeAnalytics> {
  const res = await api.get<PostcodeAnalytics>(
    `/analytics/postcode/${encodeURIComponent(postcode)}/summary`
  );
  return res.data;
}

export async function scrapeArea(
  partial: string,
  opts?: { pages?: number; linkCount?: number; maxPostcodes?: number; floorplan?: boolean; extraFeatures?: boolean; saveParquet?: boolean; skipExisting?: boolean; force?: boolean }
): Promise<AreaScrapeResponse> {
  const params: Record<string, number | boolean> = {};
  if (opts?.pages) params.pages = opts.pages;
  if (opts?.linkCount !== undefined) params.link_count = opts.linkCount;
  if (opts?.maxPostcodes !== undefined) params.max_postcodes = opts.maxPostcodes;
  if (opts?.floorplan) params.floorplan = true;
  if (opts?.extraFeatures) params.extra_features = true;
  if (opts?.saveParquet) params.save_parquet = true;
  if (opts?.skipExisting === false) params.skip_existing = false;
  if (opts?.force) params.force = true;
  const res = await api.post<AreaScrapeResponse>(
    `/scrape/area/${encodeURIComponent(partial)}`,
    null,
    { params }
  );
  return res.data;
}

export async function suggestPostcodes(
  partial: string
): Promise<string[]> {
  const res = await api.get<string[]>(
    `/postcodes/suggest/${encodeURIComponent(partial)}`
  );
  return res.data;
}

export async function getProperties(
  postcode: string
): Promise<PropertyDetail[]> {
  const res = await api.get<PropertyDetail[]>("/properties", {
    params: { postcode, limit: 0 },
  });
  return res.data;
}

export async function getMarketOverview(): Promise<MarketOverview> {
  const res = await api.get<MarketOverview>("/analytics/market-overview");
  return res.data;
}

export async function getProperty(id: number): Promise<PropertyDetail> {
  const res = await api.get<PropertyDetail>(`/properties/${id}`);
  return res.data;
}

export async function getSimilarProperties(
  id: number,
  limit = 5
): Promise<PropertyBrief[]> {
  const res = await api.get<PropertyBrief[]>(`/properties/${id}/similar`, {
    params: { limit },
  });
  return res.data;
}

export interface ExportResponse {
  message: string;
  properties_exported: number;
  files_written: number;
  output_dir: string;
}

export async function exportSalesData(
  postcode: string
): Promise<ExportResponse> {
  const res = await api.post<ExportResponse>(
    `/export/${encodeURIComponent(postcode)}`
  );
  return res.data;
}

export async function getHousingInsights(
  filters: HousingInsightsFilters = {}
): Promise<HousingInsightsResponse> {
  const params: Record<string, string | number | boolean> = {};
  if (filters.property_type) params.property_type = filters.property_type;
  if (filters.min_bedrooms !== undefined) params.min_bedrooms = filters.min_bedrooms;
  if (filters.max_bedrooms !== undefined) params.max_bedrooms = filters.max_bedrooms;
  if (filters.min_bathrooms !== undefined) params.min_bathrooms = filters.min_bathrooms;
  if (filters.max_bathrooms !== undefined) params.max_bathrooms = filters.max_bathrooms;
  if (filters.min_price !== undefined) params.min_price = filters.min_price;
  if (filters.max_price !== undefined) params.max_price = filters.max_price;
  if (filters.postcode_prefix) params.postcode_prefix = filters.postcode_prefix;
  if (filters.tenure) params.tenure = filters.tenure;
  if (filters.epc_rating) params.epc_rating = filters.epc_rating;
  if (filters.has_garden !== undefined) params.has_garden = filters.has_garden;
  if (filters.has_parking !== undefined) params.has_parking = filters.has_parking;
  if (filters.chain_free !== undefined) params.chain_free = filters.chain_free;
  const res = await api.get<HousingInsightsResponse>("/analytics/housing-insights", { params });
  return res.data;
}

export async function enrichEPC(
  postcode: string
): Promise<EPCEnrichmentResponse> {
  const res = await api.post<EPCEnrichmentResponse>(
    `/enrich/epc/${encodeURIComponent(postcode)}`
  );
  return res.data;
}

export async function getPropertiesGeo(
  postcode?: string,
  limit = 500,
): Promise<PropertyGeoPoint[]> {
  const params: Record<string, string | number> = { limit };
  if (postcode) params.postcode = postcode;
  const res = await api.get<PropertyGeoPoint[]>("/properties/geo", { params });
  return res.data;
}

export async function getFloodRisk(
  postcode: string,
): Promise<FloodRiskResponse> {
  const res = await api.get<FloodRiskResponse>(
    `/analytics/postcode/${encodeURIComponent(postcode)}/flood-risk`
  );
  return res.data;
}

export async function getGrowthData(
  postcode: string,
): Promise<PostcodeGrowthResponse> {
  const res = await api.get<PostcodeGrowthResponse>(
    `/analytics/postcode/${encodeURIComponent(postcode)}/growth`
  );
  return res.data;
}

export async function getGrowthLeaderboard(
  limit = 20,
  period = 5,
): Promise<GrowthLeaderboardEntry[]> {
  const res = await api.get<GrowthLeaderboardEntry[]>(
    "/analytics/growth-leaderboard",
    { params: { limit, period } }
  );
  return res.data;
}

export async function getPlanningApplications(
  postcode: string
): Promise<PlanningResponse> {
  const res = await api.get<PlanningResponse>(
    `/analytics/postcode/${encodeURIComponent(postcode)}/planning`
  );
  return res.data;
}

export async function getPropertyListing(
  propertyId: number,
): Promise<PropertyListingResponse> {
  const res = await api.get<PropertyListingResponse>(
    `/properties/${propertyId}/listing`
  );
  return res.data;
}

export async function enrichTransport(
  postcode: string
): Promise<TransportEnrichmentResponse> {
  const res = await api.post<TransportEnrichmentResponse>(
    `/enrich/transport/${encodeURIComponent(postcode)}`
  );
  return res.data;
}

export async function getCrimeData(
  postcode: string
): Promise<CrimeSummaryResponse> {
  const res = await api.get<CrimeSummaryResponse>(
    `/analytics/postcode/${encodeURIComponent(postcode)}/crime`
  );
  return res.data;
}

// Modelling

export async function getModelFeatures(): Promise<AvailableFeaturesResponse> {
  const res = await api.get<AvailableFeaturesResponse>("/model/features");
  return res.data;
}

export async function trainModel(
  request: TrainRequest
): Promise<TrainResponse> {
  const res = await api.post<TrainResponse>("/model/train", request);
  return res.data;
}

export async function predictProperty(
  modelId: string,
  propertyId: number,
  predictionDate?: string
): Promise<SinglePredictionResponse> {
  const params: Record<string, unknown> = { property_id: propertyId };
  if (predictionDate) params.prediction_date = predictionDate;
  const res = await api.get<SinglePredictionResponse>(
    `/model/${modelId}/predict`,
    { params }
  );
  return res.data;
}

export async function predictPostcode(
  modelId: string,
  postcode: string,
  predictionDate?: string,
  limit?: number
): Promise<PostcodePredictionResponse> {
  const params: Record<string, unknown> = { postcode };
  if (predictionDate) params.prediction_date = predictionDate;
  if (limit) params.limit = limit;
  const res = await api.get<PostcodePredictionResponse>(
    `/model/${modelId}/predict-postcode`,
    { params }
  );
  return res.data;
}
