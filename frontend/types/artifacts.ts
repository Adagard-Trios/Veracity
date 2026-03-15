export interface MarketTrendsPayload {
  trendLines: Array<{
    label: string;
    data: Array<{ date: string; value: number }>;
  }>;
  leadingIndicators: Array<{ label: string; direction: 'up' | 'down' | 'flat'; magnitude: number }>;
}

export interface CompetitivePayload {
  competitors: Array<{
    name: string;
    features: Record<string, boolean | string>;
    lastUpdated: string;
  }>;
  featureColumns: string[];
}

export interface WinLossPayload {
  reasons: Array<{ reason: string; wins: number; losses: number }>;
  buyerSentiment: Array<{ label: string; score: number }>;
}

export interface PricingPayload {
  matrix: Array<{
    competitor: string;
    tiers: Array<{ name: string; price: number | null; willingnessScore: number }>;
  }>;
}

export interface PositioningPayload {
  gaps: Array<{ dimension: string; ourScore: number; marketExpectation: number; delta: number }>;
  messagingSuggestions: string[];
}

export interface AdjacentMarketsPayload {
  threats: Array<{
    category: string;
    source: string;
    threatLevel: 'low' | 'medium' | 'high';
    size: number; // for treemap
  }>;
}

export type ArtifactPayload =
  | MarketTrendsPayload
  | CompetitivePayload
  | WinLossPayload
  | PricingPayload
  | PositioningPayload
  | AdjacentMarketsPayload;
