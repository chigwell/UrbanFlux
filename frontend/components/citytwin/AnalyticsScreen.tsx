"use client";

import { Maximize2Icon } from "lucide-react";
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";
import {
  ExpandableScreen,
  ExpandableScreenContent,
  ExpandableScreenTrigger,
} from "@/components/ui/expandable-screen";
import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import type {
  CityTwinImpact,
  CityTwinImpactMetric,
  CityTwinMetrics,
} from "@/lib/cityTwinMap";
import {
  ImpactMetricCards,
  MetricTiles,
  impactMessage,
  metricSign,
  parseMetricNumber,
} from "./impact-metrics";

interface AnalyticsScreenProps {
  scenario: string;
  metrics: CityTwinMetrics | null;
  impact: CityTwinImpact | null;
  report: string;
  /** Unique per mount — two ExpandableScreens sharing a layoutId fight over the morph. */
  layoutId: string;
}

// Theme-aware so bars flip with light/dark; values resolve from globals.css.
const SIGN_COLOR: Record<ReturnType<typeof metricSign>, string> = {
  positive: "var(--uf-positive)",
  negative: "var(--uf-positive)",
  neutral: "var(--muted-foreground)",
};

const chartConfig = {
  value: { label: "Change" },
} satisfies ChartConfig;

interface ChartRow {
  name: string;
  value: number;
  display: string;
  delta: string;
  sign: ReturnType<typeof metricSign>;
}

function toChartRows(metrics: CityTwinImpactMetric[]): ChartRow[] {
  return metrics.map((metric) => ({
    name: metric.metric,
    value: parseMetricNumber(metric),
    display: metric.value,
    delta: metric.delta,
    sign: metricSign(metric),
  }));
}

function ImpactChart({ impact }: { impact: CityTwinImpact | null }) {
  if (
    impactMessage(impact) ||
    impact?.status !== "ready" ||
    !impact.metrics?.length
  ) {
    return null;
  }

  const rows = toChartRows(impact.metrics);

  return (
    <ChartContainer
      config={chartConfig}
      className="aspect-auto h-[clamp(220px,38vh,360px)] w-full"
    >
      <BarChart
        accessibilityLayer
        data={rows}
        layout="vertical"
        margin={{ left: 8, right: 56, top: 4, bottom: 4 }}
      >
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          tickLine={false}
          axisLine={false}
          width={150}
          tick={{ fontSize: 11 }}
        />
        <ReferenceLine x={0} stroke="var(--border)" />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              hideIndicator
              labelKey="name"
              formatter={(_value, _name, item) => {
                const row = item.payload as ChartRow;
                return (
                  <div className="flex flex-1 flex-col gap-0.5">
                    <span className="font-medium text-foreground tabular-nums">
                      {row.display}
                    </span>
                    <span className="text-muted-foreground">{row.delta}</span>
                  </div>
                );
              }}
            />
          }
        />
        <Bar dataKey="value" radius={4}>
          {rows.map((row) => (
            <Cell key={row.name} fill={SIGN_COLOR[row.sign]} />
          ))}
          <LabelList
            dataKey="display"
            position="right"
            offset={8}
            className="fill-foreground"
            fontSize={11}
          />
        </Bar>
      </BarChart>
    </ChartContainer>
  );
}

export function AnalyticsScreen({
  scenario,
  metrics,
  impact,
  report,
  layoutId,
}: AnalyticsScreenProps) {
  return (
    <ExpandableScreen
      layoutId={layoutId}
      triggerRadius="2px"
      contentRadius="16px"
    >
      <ExpandableScreenTrigger className="w-full">
        <div className="flex w-full min-h-11 min-w-0 items-center justify-between gap-3 overflow-hidden border-[0.5px] bg-card px-4 py-3 text-left shadow-xs transition-colors hover:bg-muted">
          <span className="text-sm font-medium">Impact dashboard</span>
          <div className="flex min-w-0 items-center gap-2">
            <span className="max-w-36 truncate text-xs text-muted-foreground">
              {scenario}
            </span>
            <Maximize2Icon className="size-4 shrink-0 text-muted-foreground" />
          </div>
        </div>
      </ExpandableScreenTrigger>

      <ExpandableScreenContent
        className="border-[0.5px] bg-background text-foreground"
        closeButtonClassName="border-[0.5px] bg-card text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 py-8 sm:px-8 sm:py-10">
          <header className="flex flex-col gap-1 pr-12">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Impact analytics
            </span>
            <h2 className="text-xl font-semibold">{scenario}</h2>
          </header>

          <MetricTiles metrics={metrics} className="sm:grid-cols-3" />

          <p className="text-sm leading-relaxed text-muted-foreground">
            {report}
          </p>

          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-medium">Impact vs baseline</h3>
            <ImpactChart impact={impact} />
            <p className="text-xs text-muted-foreground">
              Bars show the raw change per metric; units differ (percentage
              points, %, °C, lives/year). Green is an improvement, red a
              regression.
            </p>
          </section>

          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-medium">Metric detail</h3>
            <ImpactMetricCards impact={impact} />
            {impact?.note ? (
              <p className="text-xs text-muted-foreground">{impact.note}</p>
            ) : null}
          </section>
        </div>
      </ExpandableScreenContent>
    </ExpandableScreen>
  );
}
