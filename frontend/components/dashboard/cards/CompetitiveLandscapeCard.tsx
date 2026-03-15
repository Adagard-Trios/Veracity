'use client';

import { useMemo } from 'react';
import { ArtifactCard } from '../ArtifactCard';
import { useAppStore } from '@/store';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Check, X } from 'lucide-react';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

type CompetitorRow = {
  name: string;
  [feature: string]: any;
};

export function CompetitiveLandscapeCard() {
  const artifact = useAppStore((s) => s.artifacts.competitive_landscape);

  const { data, columns } = useMemo(() => {
    if (!artifact) return { data: [], columns: [] };

    const columnHelper = createColumnHelper<CompetitorRow>();
    
    const cols = [
      columnHelper.accessor('name', {
        header: 'Competitor',
        cell: (info) => <div className="font-medium">{info.getValue()}</div>,
      }),
      ...artifact.featureColumns.map((feature) =>
        columnHelper.accessor(feature, {
          header: feature,
          cell: (info) => {
            const val = info.getValue();
            if (val === true) return <Check className="h-4 w-4 text-green-500" />;
            if (val === false) return <X className="h-4 w-4 text-red-500/50" />;
            return <span className="text-muted-foreground">{val}</span>;
          },
        })
      ),
    ];

    const rows: CompetitorRow[] = artifact.competitors.map((comp) => ({
      name: comp.name,
      ...comp.features,
    }));

    return { data: rows, columns: cols };
  }, [artifact]);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <ArtifactCard title="Competitive Landscape" agentId={3} domain="competitive_landscape">
      {artifact ? (
        <div className="pt-4 w-full h-full">
          <ScrollArea className="h-[250px] w-full rounded-md border">
            <Table>
              <TableHeader className="bg-muted/50 sticky top-0 z-10 hidden md:table-header-group">
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id} className="whitespace-nowrap text-xs font-semibold">
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {table.getRowModel().rows?.length ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow key={row.id} data-state={row.getIsSelected() && 'selected'}>
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id} className="whitespace-nowrap py-3">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      No results.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      ) : null}
    </ArtifactCard>
  );
}
