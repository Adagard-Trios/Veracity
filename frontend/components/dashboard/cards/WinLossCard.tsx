'use client';

import { ArtifactCard } from '../ArtifactCard';
import { useAppStore } from '@/store';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import { Badge } from '@/components/ui/badge';

export function WinLossCard() {
  const artifact = useAppStore((s) => s.artifacts.win_loss);

  return (
    <ArtifactCard title="Win / Loss Analysis" agentId={4} domain="win_loss">
      {artifact ? (
        <div className="flex flex-col h-full w-full gap-4 pt-4">
          <div className="flex gap-2 flex-wrap mb-2">
            {artifact.buyerSentiment.map((sent) => (
              <Badge key={sent.label} variant={sent.score > 60 ? 'default' : sent.score < 50 ? 'destructive' : 'secondary'}>
                {sent.label}: {sent.score}%
              </Badge>
            ))}
          </div>

          <div className="h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={artifact.reasons} margin={{ top: 5, right: 0, bottom: 5, left: -20 }} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="hsl(var(--border))" />
                <XAxis type="number" fontSize={12} tickLine={false} axisLine={false} fill="hsl(var(--muted-foreground))" />
                <YAxis dataKey="reason" type="category" width={80} fontSize={12} tickLine={false} axisLine={false} fill="hsl(var(--muted-foreground))" />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'hsl(var(--background))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                  cursor={{ fill: 'hsl(var(--muted)/0.4)' }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="wins" name="Wins" fill="#16a34a" radius={[0, 4, 4, 0]} barSize={12} />
                <Bar dataKey="losses" name="Losses" fill="#ef4444" radius={[0, 4, 4, 0]} barSize={12} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
    </ArtifactCard>
  );
}
