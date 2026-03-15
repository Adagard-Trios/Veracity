'use client';

import dynamic from 'next/dynamic';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import { MarketTrendsCard } from './cards/MarketTrendsCard';
import { CompetitiveLandscapeCard } from './cards/CompetitiveLandscapeCard';
import { WinLossCard } from './cards/WinLossCard';
import { PricingPackagingCard } from './cards/PricingPackagingCard';
import { PositioningCard } from './cards/PositioningCard';
import { AdjacentMarketsCard } from './cards/AdjacentMarketsCard';

const ResponsiveGridLayout: any = dynamic(
  () => import('react-grid-layout/legacy').then((mod) => {
    const ReactGridLayout = mod as any;
    const Responsive = ReactGridLayout.Responsive || ReactGridLayout.default?.Responsive;
    const WidthProvider = ReactGridLayout.WidthProvider || ReactGridLayout.default?.WidthProvider;
    return WidthProvider(Responsive);
  }),
  { ssr: false }
);

const layout = [
  { i: 'market', x: 0, y: 0, w: 6, h: 2 },
  { i: 'competitive', x: 6, y: 0, w: 6, h: 2 },
  { i: 'winloss', x: 0, y: 2, w: 4, h: 2 },
  { i: 'pricing', x: 4, y: 2, w: 4, h: 2 },
  { i: 'positioning', x: 8, y: 2, w: 4, h: 2 },
  { i: 'adjacent', x: 0, y: 4, w: 12, h: 2 },
];

const LAYOUTS = { lg: layout };
const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 };
const COLS = { lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 };
const MARGIN = [16, 16] as const;
const CONTAINER_PADDING = [0, 0] as const;

export function DashboardGrid() {
  return (
    <div className="w-full h-full pb-8">
      <ResponsiveGridLayout
        className="layout"
        layouts={LAYOUTS}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={150}
        containerPadding={CONTAINER_PADDING}
        margin={MARGIN}
        isDraggable
        isResizable
      >
        <div key="market"><MarketTrendsCard /></div>
        <div key="competitive"><CompetitiveLandscapeCard /></div>
        <div key="winloss"><WinLossCard /></div>
        <div key="pricing"><PricingPackagingCard /></div>
        <div key="positioning"><PositioningCard /></div>
        <div key="adjacent"><AdjacentMarketsCard /></div>
      </ResponsiveGridLayout>
    </div>
  );
}
