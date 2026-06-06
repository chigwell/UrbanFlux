"use client";

import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface CollapsiblePanelProps {
  title: string;
  meta?: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: React.ReactNode;
}

export function CollapsiblePanel({
  title,
  meta,
  defaultOpen = false,
  className,
  children,
}: CollapsiblePanelProps) {
  return (
    <Collapsible
      defaultOpen={defaultOpen}
      className={cn("group bg-card text-card-foreground shadow-xs", className)}
    >
      <CollapsibleTrigger className="flex w-full min-h-11 cursor-pointer items-center justify-between gap-3 border-[0.5px] px-4 py-3 text-left transition-colors hover:bg-muted/40">
        <span className="text-sm font-medium">{title}</span>
        <div className="flex min-w-0 items-center gap-2">
          {meta ? (
            <span className="max-w-36 truncate text-xs text-muted-foreground">
              {meta}
            </span>
          ) : null}
          <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="overflow-hidden px-4 py-4 data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down border-[0.5px] border-t-0 ">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
