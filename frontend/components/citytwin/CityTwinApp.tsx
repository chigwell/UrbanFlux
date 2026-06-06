"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { ArrowLeftIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  CityTwinHandle,
  CityTwinMetrics,
  CityTwinPills,
  CityTwinPopulation,
  CityTwinSettingKey,
  CityTwinSettings,
} from "@/lib/cityTwinMap";
import { ControlsCard } from "./ControlsCard";
import { DashboardCard } from "./DashboardCard";
import { IntroCard } from "./IntroCard";
import { LegendCard } from "./LegendCard";
import { PopulationCard } from "./PopulationCard";
import { StatusCard } from "./StatusCard";

const DEFAULT_SETTINGS: CityTwinSettings = {
  density: 64,
  green: 35,
  parking: 18,
  street: 35,
  alignment: 72,
  height: 58,
};

export function CityTwinApp() {
  const { resolvedTheme, setTheme } = useTheme();
  const handleRef = useRef<CityTwinHandle | null>(null);

  const [mounted, setMounted] = useState(false);
  const [settings, setSettings] = useState<CityTwinSettings>(DEFAULT_SETTINGS);
  const [allowWater, setAllowWater] = useState(false);
  const [progress, setProgress] = useState(8);
  const [status, setStatus] = useState("Booting the CityTwin engine…");
  const [pills, setPills] = useState<CityTwinPills>({
    roads: 0,
    water: 0,
    anchors: 0,
  });
  const [metrics, setMetrics] = useState<CityTwinMetrics | null>(null);
  const [population, setPopulation] = useState<CityTwinPopulation | null>(null);
  const [scenario, setScenario] = useState("No scenario yet");
  const [report, setReport] = useState("Loading the demo zone…");
  const [hint, setHint] = useState(
    "Click at least four points. Drag vertices to reshape.",
  );

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    let cancelled = false;
    const initialDark = document.documentElement.classList.contains("dark");

    import("@/lib/cityTwinMap").then(({ initCityTwinMap }) => {
      if (cancelled) {
        return;
      }
      const handle = initCityTwinMap({
        container: "map",
        initialTheme: initialDark ? "dark" : "light",
        initialAllowWater: false,
        initialSettings: DEFAULT_SETTINGS,
        onStatus: (value, text) => {
          setProgress(value);
          setStatus(text);
        },
        onMetrics: setMetrics,
        onPopulation: setPopulation,
        onScenario: setScenario,
        onReport: setReport,
        onHint: setHint,
        onPills: setPills,
        onToast: (text) => toast(text),
      });
      handleRef.current = handle;
    });

    return () => {
      cancelled = true;
      handleRef.current?.destroy();
      handleRef.current = null;
    };
  }, []);

  const isDark = mounted ? resolvedTheme === "dark" : false;

  const handleSetting = (key: CityTwinSettingKey, value: number) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    handleRef.current?.setSetting(key, value);
  };

  const handleAllowWater = (on: boolean) => {
    setAllowWater(on);
    handleRef.current?.setAllowWater(on);
  };

  const handleToggleTheme = (dark: boolean) => {
    setTheme(dark ? "dark" : "light");
    handleRef.current?.setTheme(dark ? "dark" : "light");
  };

  return (
    <div className="relative h-dvh w-full overflow-hidden bg-background">
      <div id="map" />

      <div className="absolute left-4 top-4 z-10 flex w-[min(21rem,calc(100vw-2rem))] flex-col gap-2.5">
        <div className="flex w-fit items-center justify-between gap-2  border-[0.5px] bg-card px-3 py-2 shadow-sm">
          <Button asChild size="sm" variant="ghost">
            <Link href="/" className="hover:bg-transparent">
              <ArrowLeftIcon data-icon="inline-start" />
              Home
            </Link>
          </Button>
        </div>
        <IntroCard />
        <StatusCard progress={progress} status={status} pills={pills} />
      </div>

      <div className="absolute right-4 top-4 z-10 flex max-h-[calc(100dvh-2rem)] w-[min(22rem,calc(100vw-2rem))] flex-col gap-2.5 overflow-y-auto pb-2 *:shrink-0">
        <ControlsCard
          settings={settings}
          allowWater={allowWater}
          isDark={isDark}
          onSetting={handleSetting}
          onAllowWater={handleAllowWater}
          onToggleTheme={handleToggleTheme}
          onDemo={() => handleRef.current?.loadDemo()}
          onUndo={() => handleRef.current?.undo()}
          onClear={() => handleRef.current?.clearZone()}
          onFit={() => handleRef.current?.fit()}
        />
        <LegendCard />
        <PopulationCard population={population} />
        <DashboardCard scenario={scenario} metrics={metrics} report={report} />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-5 z-10 flex justify-center px-4">
        <p className="pointer-events-auto max-w-xl border-[0.5px] bg-card px-4 py-2 text-center text-xs text-muted-foreground">
          {hint}
        </p>
      </div>
    </div>
  );
}
