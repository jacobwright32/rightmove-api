import { useQuery } from "@tanstack/react-query";
import {
  getCrimeData,
  getFloodRisk,
  getGrowthData,
  getMarketOverview,
  getGrowthLeaderboard,
  getPlanningApplications,
  getProperty,
  getPropertyListing,
  getSimilarProperties,
} from "../api/client";
import type { PropertyBrief } from "../api/types";

export function usePropertyQuery(id: number) {
  return useQuery({
    queryKey: ["property", id],
    queryFn: () => getProperty(id),
    enabled: id > 0,
  });
}

export function useSimilarQuery(id: number) {
  return useQuery({
    queryKey: ["similar", id],
    queryFn: () => getSimilarProperties(id).catch(() => [] as PropertyBrief[]),
    enabled: id > 0,
  });
}

export function useListingQuery(propertyId: number) {
  return useQuery({
    queryKey: ["listing", propertyId],
    queryFn: () => getPropertyListing(propertyId),
    enabled: propertyId > 0,
  });
}

export function useGrowthQuery(postcode: string) {
  return useQuery({
    queryKey: ["growth", postcode],
    queryFn: () => getGrowthData(postcode),
    enabled: !!postcode,
  });
}

export function useFloodRiskQuery(postcode: string, enabled: boolean) {
  return useQuery({
    queryKey: ["floodRisk", postcode],
    queryFn: () => getFloodRisk(postcode),
    enabled: enabled && !!postcode,
  });
}

export function useCrimeQuery(postcode: string, enabled: boolean) {
  return useQuery({
    queryKey: ["crime", postcode],
    queryFn: () => getCrimeData(postcode),
    enabled: enabled && !!postcode,
    refetchInterval: (query) => {
      // Poll every 4s while backend is fetching
      const data = query.state.data;
      return data?.fetching ? 4000 : false;
    },
  });
}

export function usePlanningQuery(postcode: string, enabled: boolean) {
  return useQuery({
    queryKey: ["planning", postcode],
    queryFn: () => getPlanningApplications(postcode),
    enabled: enabled && !!postcode,
  });
}

export function useMarketOverview() {
  return useQuery({
    queryKey: ["marketOverview"],
    queryFn: getMarketOverview,
    staleTime: 30 * 60 * 1000, // 30 min
  });
}

export function useGrowthLeaderboard(limit: number, minSales: number) {
  return useQuery({
    queryKey: ["growthLeaderboard", limit, minSales],
    queryFn: () => getGrowthLeaderboard(limit, minSales),
    staleTime: 30 * 60 * 1000,
  });
}
