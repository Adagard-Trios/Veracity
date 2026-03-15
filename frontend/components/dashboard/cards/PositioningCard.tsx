'use client';

import { ArtifactCard } from '../ArtifactCard';
import { useAppStore } from '@/store';
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  Legend
} from 'recharts';

export function PositioningCard() {
  const artifact = useAppStore((s) => s.artifacts.positioning);

  return (
    <ArtifactCard title="Positioning Scorecard" agentId={6} domain="positioning">
      {artifact ? (
        <div className="flex w-full h-full pt-4 gap-4">
          <div className="flex-1 h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart cx="50%" cy="50%" outerRadius="70%" data={artifact.gaps}>
                <PolarGrid stroke="hsl(var(--border))" />
                <PolarAngleAxis dataKey="dimension" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
                <PolarRadiusAxis angle={30} domain={[0, 10]} tick={false} axisLine={false} />
                <Radar name="Our Score" dataKey="ourScore" stroke="#2563eb" fill="#3b82f6" fillOpacity={0.5} />
                <Radar name="Market Element" dataKey="marketExpectation" stroke="#16a34a" fill="#22c55e" fillOpacity={0.3} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'hsl(var(--background))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: '10px' }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
          <div className="w-[180px] flex flex-col gap-2 overflow-y-auto">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Top Suggestions</h4>
            {artifact.messagingSuggestions.map((msg, idx) => (
              <div key={idx} className="bg-muted text-xs p-2 rounded-md border border-border/50 shadow-sm">
                {msg}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </ArtifactCard>
  );
}
