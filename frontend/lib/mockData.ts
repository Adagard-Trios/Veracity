import type {
  MarketTrendsPayload,
  CompetitivePayload,
  WinLossPayload,
  PricingPayload,
  PositioningPayload,
  AdjacentMarketsPayload,
} from '@/types/artifacts';
import type { Domain } from '@/types/agents';

export const mockMarketTrends: MarketTrendsPayload = {
  trendLines: [
    {
      label: 'AI Adoption',
      data: [
        { date: '2023-Q1', value: 20 },
        { date: '2023-Q2', value: 35 },
        { date: '2023-Q3', value: 55 },
        { date: '2023-Q4', value: 80 },
        { date: '2024-Q1', value: 110 },
      ],
    },
    {
      label: 'Legacy Systems',
      data: [
        { date: '2023-Q1', value: 90 },
        { date: '2023-Q2', value: 85 },
        { date: '2023-Q3', value: 75 },
        { date: '2023-Q4', value: 60 },
        { date: '2024-Q1', value: 45 },
      ],
    },
  ],
  leadingIndicators: [
    { label: 'Cloud Shift', direction: 'up', magnitude: 8 },
    { label: 'Data Silos', direction: 'down', magnitude: -5 },
    { label: 'Security Spends', direction: 'up', magnitude: 3 },
  ],
};

export const mockCompetitive: CompetitivePayload = {
  featureColumns: ['AI Copilot', 'SSO', 'Analytics', 'Mobile App'],
  competitors: [
    {
      name: 'Our Product',
      lastUpdated: '2024-03-01T12:00:00Z',
      features: {
        'AI Copilot': true,
        'SSO': true,
        'Analytics': 'Advanced',
        'Mobile App': true,
      },
    },
    {
      name: 'Competitor A',
      lastUpdated: '2024-02-15T12:00:00Z',
      features: {
        'AI Copilot': false,
        'SSO': true,
        'Analytics': 'Basic',
        'Mobile App': false,
      },
    },
    {
      name: 'Competitor B',
      lastUpdated: '2024-02-28T12:00:00Z',
      features: {
        'AI Copilot': true,
        'SSO': false,
        'Analytics': 'Basic',
        'Mobile App': true,
      },
    },
  ],
};

export const mockWinLoss: WinLossPayload = {
  reasons: [
    { reason: 'Price', wins: 20, losses: 40 },
    { reason: 'Features', wins: 50, losses: 10 },
    { reason: 'Support', wins: 30, losses: 5 },
    { reason: 'UI/UX', wins: 15, losses: 25 },
  ],
  buyerSentiment: [
    { label: 'Innovative', score: 85 },
    { label: 'Reliable', score: 60 },
    { label: 'Expensive', score: 40 },
  ],
};

export const mockPricing: PricingPayload = {
  matrix: [
    {
      competitor: 'Our Product',
      tiers: [
        { name: 'Starter', price: 49, willingnessScore: 80 },
        { name: 'Pro', price: 99, willingnessScore: 65 },
        { name: 'Enterprise', price: 299, willingnessScore: 90 },
      ],
    },
    {
      competitor: 'Competitor A',
      tiers: [
        { name: 'Starter', price: 29, willingnessScore: 95 },
        { name: 'Pro', price: 79, willingnessScore: 75 },
        { name: 'Enterprise', price: null, willingnessScore: 40 },
      ],
    },
  ],
};

export const mockPositioning: PositioningPayload = {
  gaps: [
    { dimension: 'Scalability', ourScore: 9, marketExpectation: 7, delta: 2 },
    { dimension: 'Ease of Use', ourScore: 6, marketExpectation: 8, delta: -2 },
    { dimension: 'Customization', ourScore: 8, marketExpectation: 5, delta: 3 },
    { dimension: 'Integration', ourScore: 4, marketExpectation: 7, delta: -3 },
  ],
  messagingSuggestions: [
    'Highlight superior scalability tailored for growing teams.',
    'Acknowledge learning curve but emphasize deep customization.',
    'Focus on robust AI features that competitors lack.',
  ],
};

export const mockAdjacentMarkets: AdjacentMarketsPayload = {
  threats: [
    { category: 'CRM Integration', source: 'Startups', threatLevel: 'medium', size: 40 },
    { category: 'Data Warehousing', source: 'Tech Giants', threatLevel: 'high', size: 80 },
    { category: 'Niche Analytics', source: 'Boutique Firms', threatLevel: 'low', size: 15 },
    { category: 'Workflow Automation', source: 'Open Source', threatLevel: 'medium', size: 30 },
  ],
};

export const mockArtifacts: Record<Domain, any> = {
  market_trends: mockMarketTrends,
  competitive_landscape: mockCompetitive,
  win_loss: mockWinLoss,
  pricing_packaging: mockPricing,
  positioning: mockPositioning,
  adjacent_markets: mockAdjacentMarkets,
};
