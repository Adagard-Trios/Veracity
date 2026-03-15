'use client';

import { useMemo } from 'react';
import { ArtifactCard } from '../ArtifactCard';
import { useAppStore } from '@/store';
import { ResponsiveTreeMap } from '@nivo/treemap';

export function AdjacentMarketsCard() {
  const artifact = useAppStore((s) => s.artifacts.adjacent_markets);

  const treemapData = useMemo(() => {
    if (!artifact) return { name: 'root', children: [] };
    
    // Group by threat level or category
    return {
      name: 'Markets',
      children: artifact.threats.map((threat) => ({
        name: threat.category,
        source: threat.source,
        threatLevel: threat.threatLevel,
        loc: threat.size, // Treemap relies on 'loc' or 'value' mapping usually, let's use value
      }))
    };
  }, [artifact]);

  const getThreatColor = (node: any) => {
    const level = node.data.threatLevel;
    if (level === 'high') return '#ef4444'; // red-500
    if (level === 'medium') return '#f59e0b'; // amber-500
    return '#3b82f6'; // blue-500
  };

  return (
    <ArtifactCard title="Adjacent Market Threats" agentId={7} domain="adjacent_markets">
      {artifact ? (
        <div className="h-[250px] w-full pt-4">
          <ResponsiveTreeMap
            data={treemapData}
            identity="name"
            value="loc"
            valueFormat=".02s"
            margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
            labelSkipSize={12}
            labelTextColor={{ from: 'color', modifiers: [['darker', 3]] }}
            parentLabelPosition="left"
            parentLabelTextColor={{ from: 'color', modifiers: [['darker', 2]] }}
            colors={getThreatColor}
            borderColor={{ from: 'color', modifiers: [['darker', 0.1]] }}
            theme={{
              labels: { text: { fontSize: 13, fontWeight: 500, fill: '#ffffff' } },
              tooltip: { container: { background: 'hsl(var(--background))', color: 'hsl(var(--foreground))', fontSize: 12 } }
            }}
          />
        </div>
      ) : null}
    </ArtifactCard>
  );
}
