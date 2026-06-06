"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface BottomSheetProps {
  /** Always-visible row shown next to the drag handle in the peek area. */
  peek: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  expanded?: boolean;
  onExpandedChange?: (expanded: boolean) => void;
}

const DRAG_THRESHOLD = 56;
const TAP_TOLERANCE = 6;

/**
 * A dependency-free, draggable bottom sheet for mobile. The map stays
 * interactive in the area above the collapsed peek; drag (or tap) the handle to
 * expand to a tall, scrollable panel. Rendered only below `md` by the caller.
 */
export function BottomSheet({
  peek,
  children,
  className,
  expanded: controlledExpanded,
  onExpandedChange,
}: BottomSheetProps) {
  const [internalExpanded, setInternalExpanded] = useState(false);
  const [drag, setDrag] = useState<number | null>(null);
  const [peekHeight, setPeekHeight] = useState(88);
  const headerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const startY = useRef(0);
  const expanded = controlledExpanded ?? internalExpanded;

  // Keep the collapsed translate exactly equal to the header height, so the peek
  // shows the handle + summary and nothing more, whatever the summary text is.
  useEffect(() => {
    const header = headerRef.current;
    if (!header) {
      return;
    }
    const measure = () => setPeekHeight(header.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  const collapsedTranslate = `calc(100% - ${peekHeight}px)`;
  const base = expanded ? "0px" : collapsedTranslate;
  const translate = drag === null ? base : `calc(${base} + ${drag}px)`;

  const setExpandedState = (
    next: boolean | ((value: boolean) => boolean),
  ) => {
    const resolved = typeof next === "function" ? next(expanded) : next;

    if (controlledExpanded === undefined) {
      setInternalExpanded(resolved);
    }

    onExpandedChange?.(resolved);
  };

  const onPointerDown = (event: React.PointerEvent) => {
    dragging.current = true;
    startY.current = event.clientY;
    setDrag(0);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent) => {
    if (!dragging.current) {
      return;
    }
    let delta = event.clientY - startY.current;
    // Only allow dragging in the direction that changes state.
    delta = expanded ? Math.max(0, delta) : Math.min(0, delta);
    setDrag(Math.max(-800, Math.min(800, delta)));
  };

  const onPointerUp = () => {
    if (!dragging.current) {
      return;
    }
    dragging.current = false;
    const delta = drag ?? 0;
    if (Math.abs(delta) < TAP_TOLERANCE) {
      setExpandedState((value) => !value); // treat as a tap
    } else if (expanded && delta > DRAG_THRESHOLD) {
      setExpandedState(false);
    } else if (!expanded && delta < -DRAG_THRESHOLD) {
      setExpandedState(true);
    }
    setDrag(null);
  };

  return (
    <div
      className={cn(
        "fixed inset-x-0 bottom-0 z-20 flex h-[85dvh] flex-col border-[0.5px] bg-card shadow-lg md:hidden",
        drag === null && "transition-transform duration-300 ease-out",
        className,
      )}
      style={{ transform: `translateY(${translate})` }}
    >
      <div
        ref={headerRef}
        className="flex shrink-0 cursor-grab touch-none flex-col gap-2 px-4 pb-3 pt-2.5 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div className="mx-auto h-1.5 w-10 rounded-full bg-muted-foreground/30" />
        {peek}
      </div>
      <div className="flex-1 overflow-y-auto overscroll-contain px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        {children}
      </div>
    </div>
  );
}
