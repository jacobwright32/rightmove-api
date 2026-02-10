import axios from "axios";
import type {
  AreaScrapeResponse,
  MarketOverview,
  PostcodeAnalytics,
  PostcodeStatus,
  PropertyBrief,
  PropertyDetail,
  ScrapeResponse,
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
  opts?: { pages?: number; linkCount?: number; floorplan?: boolean; extraFeatures?: boolean; saveParquet?: boolean }
): Promise<ScrapeResponse> {
  const params: Record<string, number | boolean> = {};
  if (opts?.pages) params.pages = opts.pages;
  if (opts?.linkCount !== undefined) params.link_count = opts.linkCount;
  if (opts?.floorplan) params.floorplan = true;
  if (opts?.extraFeatures) params.extra_features = true;
  if (opts?.saveParquet) params.save_parquet = true;
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
  opts?: { pages?: number; linkCount?: number; maxPostcodes?: number; floorplan?: boolean; extraFeatures?: boolean; saveParquet?: boolean }
): Promise<AreaScrapeResponse> {
  const params: Record<string, number | boolean> = {};
  if (opts?.pages) params.pages = opts.pages;
  if (opts?.linkCount !== undefined) params.link_count = opts.linkCount;
  if (opts?.maxPostcodes !== undefined) params.max_postcodes = opts.maxPostcodes;
  if (opts?.floorplan) params.floorplan = true;
  if (opts?.extraFeatures) params.extra_features = true;
  if (opts?.saveParquet) params.save_parquet = true;
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
