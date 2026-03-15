'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { SourceItem } from '@/types/agents';

interface SourceTrailProps {
  sources: SourceItem[];
}

export function SourceTrail({ sources }: SourceTrailProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!sources?.length) return null;

  return (
    <div className="mt-2">
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-2 text-xs text-muted-foreground"
        onClick={() => setIsOpen(!isOpen)}
      >
        {isOpen ? <ChevronUp className="w-3 h-3 mr-1" /> : <ChevronDown className="w-3 h-3 mr-1" />}
        {sources.length} source{sources.length !== 1 ? 's' : ''}
      </Button>

      {isOpen && (
        <div className="mt-1 space-y-1 border-l-2 border-border pl-3">
          {sources.map((source, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline truncate block"
                >
                  {source.title}
                  <ExternalLink className="inline w-2.5 h-2.5 ml-1 opacity-60" />
                </a>
                <span className="text-[10px] text-muted-foreground">
                  {Math.round(source.confidence * 100)}% confidence
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
