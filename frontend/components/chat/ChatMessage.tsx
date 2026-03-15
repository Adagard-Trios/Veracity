'use client';

import { SourceTrail } from './SourceTrail';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { sanitize } from '@/lib/sanitize';
import type { SourceItem } from '@/types/agents';

export interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  clarificationChips?: string[];
  timestamp: number;
}

export function ChatMessage({ message }: { message: ChatMessageData }) {
  const isUser = message.role === 'user';

  return (
    <div className={cn("flex flex-col gap-1 w-full", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg p-3 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        <div 
           className="whitespace-pre-wrap"
           dangerouslySetInnerHTML={{ __html: sanitize(message.content) }} 
        />
        {!isUser && message.sources && <SourceTrail sources={message.sources} />}
      </div>
      {!isUser && (message.clarificationChips?.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2 mt-1">
          {message.clarificationChips?.map((chip: string, i: number) => (
            <Badge key={i} variant="outline" className="cursor-pointer hover:bg-muted" onClick={() => {/* handle chip click */}}>
              {chip}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
