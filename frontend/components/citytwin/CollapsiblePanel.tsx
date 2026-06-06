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
      className={cn(
        "overflow-hidden rounded-xl bg-card/85 text-sm ring-1 ring-foreground/10 backdrop-blur",
        className
      )}
    >
      <CollapsibleTrigger className="group flex w-full min-h-11 cursor-pointer items-center justify-between gap-3 border-b px-4 py-3 text-left">
        <span className="text-xs font-extrabold uppercase tracking-wider">
          {title}
        </span>
        <div className="flex min-w-0 items-center gap-2">
          {meta ? (
            <span className="truncate text-xs text-muted-foreground">{meta}</span>
          ) : null}
          <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-[state=open]:rotate-180" />
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 py-4">{children}</CollapsibleContent>
    </Collapsible>
  );
}
