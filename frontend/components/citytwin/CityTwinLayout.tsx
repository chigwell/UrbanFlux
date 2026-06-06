"use client";

import Link from "next/link";
import { ArrowLeftIcon, MoonIcon, SparklesIcon, SunIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import type {
  AutoImprovementMode,
  CityTwinImpact,
  CityTwinMetrics,
  CityTwinPills,
  CityTwinPopulation,
  CityTwinSettingKey,
  CityTwinSettings,
} from "@/lib/cityTwinMap";
import { BottomSheet } from "./BottomSheet";
import { ControlsCard } from "./ControlsCard";
import { DashboardCard } from "./DashboardCard";
import { IntroCard } from "./IntroCard";
import { LegendCard } from "./LegendCard";
import { PopulationCard } from "./PopulationCard";
import { StatusCard } from "./StatusCard";

interface CityTwinLayoutProps {
  isDark: boolean;
  settings: CityTwinSettings;
  allowWater: boolean;
  autoRunning: boolean;
  autoMode: AutoImprovementMode;
  controlsOpen: boolean;
  bottomSheetExpanded: boolean;
  progress: number;
  status: string;
  pills: CityTwinPills;
  metrics: CityTwinMetrics | null;
  population: CityTwinPopulation | null;
  impact: CityTwinImpact | null;
  scenario: string;
  report: string;
  hint: string;
  onControlsOpenChange: (open: boolean) => void;
  onBottomSheetExpandedChange: (expanded: boolean) => void;
  onStartAutoImprovement: () => void;
  onStopAutoImprovement: () => void;
  onRestartAutoImprovement: () => void;
  onSetting: (key: CityTwinSettingKey, value: number) => void;
  onAllowWater: (on: boolean) => void;
  onToggleTheme: (dark: boolean) => void;
  onDemo: () => void;
  onUndo: () => void;
  onClear: () => void;
  onFit: () => void;
}

export function CityTwinLayout({
  isDark,
  settings,
  allowWater,
  autoRunning,
  autoMode,
  controlsOpen,
  bottomSheetExpanded,
  progress,
  status,
  pills,
  metrics,
  population,
  impact,
  scenario,
  report,
  hint,
  onControlsOpenChange,
  onBottomSheetExpandedChange,
  onStartAutoImprovement,
  onStopAutoImprovement,
  onRestartAutoImprovement,
  onSetting,
  onAllowWater,
  onToggleTheme,
  onDemo,
  onUndo,
  onClear,
  onFit,
}: CityTwinLayoutProps) {
  const homeButton = (
    <div className="flex w-fit items-stretch gap-2 border-[0.5px] bg-card px-3 py-2 shadow-sm">
      <div className="flex items-center">
        <Button asChild size="sm" variant="ghost">
          <Link href="/" className="hover:bg-transparent">
            <ArrowLeftIcon data-icon="inline-start" />
            Home
          </Link>
        </Button>
      </div>
      <Separator orientation="vertical" />
      <div className="flex items-center gap-2 text-sm font-medium">
        {isDark ? (
          <MoonIcon className="size-4" aria-hidden />
        ) : (
          <SunIcon className="size-4" aria-hidden />
        )}
        <span className="hidden sm:inline">
          {isDark ? "Dark" : "Light"} basemap
        </span>
        <Switch
          checked={isDark}
          onCheckedChange={onToggleTheme}
          aria-label="Toggle basemap theme"
        />
      </div>
    </div>
  );

  const controlsCard = (
    <ControlsCard
      settings={settings}
      allowWater={allowWater}
      autoRunning={autoRunning}
      autoMode={autoMode}
      controlsOpen={controlsOpen}
      onControlsOpenChange={onControlsOpenChange}
      onStartAutoImprovement={onStartAutoImprovement}
      onStopAutoImprovement={onStopAutoImprovement}
      onRestartAutoImprovement={onRestartAutoImprovement}
      onSetting={onSetting}
      onAllowWater={onAllowWater}
      onDemo={onDemo}
      onUndo={onUndo}
      onClear={onClear}
      onFit={onFit}
    />
  );

  return (
    <div className="relative h-dvh w-full overflow-hidden bg-background">
      <div id="map" />

      {autoRunning ? (
        <div className="absolute left-1/2 top-3 z-40 flex -translate-x-1/2 items-center gap-2 border-[0.5px] bg-card px-3 py-2 shadow-sm">
          <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex">
            <SparklesIcon className="size-3.5" />
            Auto improvement
          </span>
          <Button size="sm" variant="destructive" onClick={onStopAutoImprovement}>
            Stop
          </Button>
          <Button size="sm" variant="outline" onClick={onRestartAutoImprovement}>
            Restart
          </Button>
        </div>
      ) : null}

      <div className="absolute left-4 top-4 z-10 hidden w-[min(21rem,calc(100vw-2rem))] flex-col gap-2.5 md:flex">
        {homeButton}
        <IntroCard />
        <StatusCard progress={progress} status={status} pills={pills} />
      </div>

      <div className="absolute right-4 top-4 z-10 hidden max-h-[calc(100dvh-2rem)] w-[min(22rem,calc(100vw-2rem))] flex-col gap-2.5 overflow-y-auto pb-2 *:shrink-0 md:flex">
        {controlsCard}
        <LegendCard />
        <PopulationCard
          population={population}
          heightAmbition={settings.height}
        />
        <DashboardCard
          scenario={scenario}
          metrics={metrics}
          impact={impact}
          report={report}
          layoutId="analytics-desktop"
        />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-5 z-10 hidden justify-center px-4 md:flex">
        <p className="pointer-events-auto max-w-xl border-[0.5px] bg-card px-4 py-2 text-center text-xs text-muted-foreground">
          {hint}
        </p>
      </div>

      <div className="absolute left-3 top-3 z-30 md:hidden">{homeButton}</div>
      <BottomSheet
        expanded={bottomSheetExpanded}
        onExpandedChange={onBottomSheetExpandedChange}
        peek={
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium">Controls &amp; insights</span>
          </div>
        }
      >
        <div className="flex flex-col gap-2.5 py-1 *:shrink-0">
          {controlsCard}
          <PopulationCard
            population={population}
            heightAmbition={settings.height}
          />
          <DashboardCard
            scenario={scenario}
            metrics={metrics}
            impact={impact}
            report={report}
            layoutId="analytics-mobile"
          />
          <StatusCard progress={progress} status={status} pills={pills} />
          <LegendCard />
          <IntroCard />
        </div>
      </BottomSheet>
    </div>
  );
}
