'use client';

import { ArtifactCard } from '../ArtifactCard';
import { useAppStore } from '@/store';
import { ResponsiveHeatMap } from '@nivo/heatmap';

export function PricingPackagingCard() {
  const artifact = useAppStore((s) => s.artifacts.pricing_packaging);

  // Transform matrix data for Nivo Heatmap
  // Nivo v0.80+ expects: [{ id: 'Competitor A', data: [{ x: 'Starter', y: 29 }, ...] }, ...]
  const heatmapData = artifact?.matrix.map((row) => {
    return {
      id: row.competitor,
      data: row.tiers.map((tier) => ({
        x: tier.name,
        y: tier.price || 0,
      }))
    };
  }) || [];

  return (
    <ArtifactCard title="Pricing & Packaging" agentId={5} domain="pricing_packaging">
      {artifact ? (
        <div className="h-62.5 w-full pt-4">
          <ResponsiveHeatMap
            data={heatmapData}
            margin={{ top: 30, right: 20, bottom: 20, left: 90 }}
            valueFormat={(val: number) => (val > 0 ? `$${val}` : 'N/A')}
            axisTop={{
              tickSize: 5,
              tickPadding: 5,
              tickRotation: 0,
              legend: '',
              legendOffset: 46
            }}
            axisLeft={{
              tickSize: 5,
              tickPadding: 5,
              tickRotation: 0,
            }}
            colors={{
              type: 'sequential',
              scheme: 'blues',
            }}
            emptyColor="#555555"
            borderWidth={1}
            borderColor={{ from: 'color', modifiers: [['darker', 0.4]] }}
            enableLabels={true}
            labelTextColor={{ from: 'color', modifiers: [['darker', 2]] }}
            theme={{
              axis: {
                ticks: { text: { fill: 'hsl(var(--muted-foreground))', fontSize: 12 } },
              },
              labels: { text: { fontSize: 13, fontWeight: 600 } },
              tooltip: { container: { background: 'hsl(var(--background))', color: 'hsl(var(--foreground))', fontSize: 12 } }
            }}
          />
        </div>
      ) : null}
    </ArtifactCard>
  );
}
