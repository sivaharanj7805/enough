/**
 * Phase 6: Living Ecosystem — TypeScript interfaces matching backend Pydantic models.
 */

export interface RiverData {
  from_cluster_id: string;
  to_cluster_id: string;
  forward_links: number;
  backward_links: number;
  total_links: number;
  bidirectional_ratio: number;
  width: number;
  quality: 'sparkling' | 'clear' | 'murky' | 'toxic';
}

export interface GrassData {
  state: 'fresh' | 'maintained' | 'overgrown' | 'dead';
  avg_days_old: number;
  oldest_post_days: number | null;
  newest_post_days: number | null;
}

export interface WeatherData {
  state: 'sunny' | 'cloudy' | 'rain' | 'storm' | 'fog';
  recent_traffic: number;
  previous_traffic: number;
  change_percent: number | null;
}

export interface AnimalData {
  type: 'birds' | 'foxes' | 'deer' | 'bees' | 'vultures';
  count: number;
  meaning: string;
}

export interface TerrainFeature {
  type: 'boulders' | 'erosion' | 'mushrooms';
  count: number;
  meaning: string;
}

export interface EcosystemVisualsResponse {
  rivers: RiverData[];
  grass: Record<string, GrassData>;
  weather: Record<string, WeatherData>;
  animals: Record<string, AnimalData[]>;
  water_quality_note: string | null;
  terrain_features: Record<string, TerrainFeature[]>;
}

/** Cluster position data used by renderers */
export interface ClusterPosition {
  id: string;
  x: number;
  y: number;
  radius: number;
}

export type ClusterPositions = Record<string, ClusterPosition>;
