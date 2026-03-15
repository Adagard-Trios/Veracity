'use client';

import { useMemo } from 'react';
import { ArtifactCard } from '../ArtifactCard';
import { useAppStore } from '@/store';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';

export function MarketTrendsCard() {
  const artifact = useAppStore((s) => s.artifacts.market_trends);

  // Transform data for Recharts: [{ date: '2023-Q1', "AI Adoption": 20, "Legacy...": 90 }, ...]
  const chartData = useMemo(() => {
    if (!artifact?.trendLines) return [];
    
    const mergedData: Record<string, any> = {};
    
    artifact.trendLines.forEach((trend) => {
      trend.data.forEach((point) => {
        if (!mergedData[point.date]) {
          mergedData[point.date] = { date: point.date };
        }
        mergedData[point.date][trend.label] = point.value;
      });
    });

    // Return as array sorted by date (assuming string sort works for Q1/Q2/etc)
    return Object.values(mergedData).sort((a, b) => a.date.localeCompare(b.date));
  }, [artifact]);

  const colors = ['#2563eb', '#16a34a', '#8b5cf6', '#d97706']; // Basic tailwind colors

  return (
    <ArtifactCard title="Market & Trends" agentId={2} domain="market_trends">
      {artifact ? (
        <div className="flex flex-col h-full w-full gap-4 pt-4">
          <div className="h-62.5 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                <XAxis 
                  dataKey="date" 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }} 
                />
                <YAxis 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }} 
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'hsl(var(--background))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                {artifact.trendLines.map((trend, idx) => (
                  <Line
                    key={trend.label}
                    type="monotone"
                    dataKey={trend.label}
                    stroke={colors[idx % colors.length]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          
          <div className="flex gap-2 flex-wrap">
            {artifact.leadingIndicators?.map((ind) => (
              <div key={ind.label} className="bg-secondary text-secondary-foreground text-xs px-3 py-1.5 rounded-full flex items-center gap-1">
                <span className={ind.direction === 'up' ? 'text-green-500' : ind.direction === 'down' ? 'text-red-500' : 'text-yellow-500'}>
                  {ind.direction === 'up' ? '↑' : ind.direction === 'down' ? '↓' : '→'}
                </span>
                {ind.label}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </ArtifactCard>
  );
}
