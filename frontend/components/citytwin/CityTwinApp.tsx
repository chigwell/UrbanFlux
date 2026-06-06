"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { ArrowLeftIcon, SparklesIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  AutoImprovementMode,
  CityTwinHandle,
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

const DEFAULT_SETTINGS: CityTwinSettings = {
  density: 64,
  green: 35,
  parking: 18,
  street: 35,
  alignment: 72,
  height: 58,
};

const AUTO_TIMING = {
  londonOverviewMs: 1600,
  pauseAfterOverviewMs: 450,
  vertexRevealMs: 900,
  fitToZoneMs: 1200,
  waitForInitialPlanTimeoutMs: 12000,
  parameterStepMs: 320,
  waitForImprovedPlanTimeoutMs: 8000,
  orbitMoveMs: 8500,
};

const SETTING_LIMITS: Record<CityTwinSettingKey, { min: number; max: number }> =
  {
    density: { min: 5, max: 100 },
    green: { min: 5, max: 80 },
    parking: { min: 0, max: 80 },
    street: { min: 0, max: 100 },
    alignment: { min: 0, max: 100 },
    height: { min: 0, max: 100 },
  };

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }

    const timer = window.setTimeout(resolve, ms);

    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });

const randomInt = (min: number, max: number) =>
  Math.floor(min + Math.random() * (max - min + 1));

const clampSetting = (key: CityTwinSettingKey, value: number) => {
  const limit = SETTING_LIMITS[key];
  return Math.max(limit.min, Math.min(limit.max, value));
};

const buildRandomGreenerSettings = (
  current: CityTwinSettings,
): CityTwinSettings => ({
  density: clampSetting("density", randomInt(58, 88)),
  green: clampSetting(
    "green",
    Math.max(current.green + randomInt(18, 32), randomInt(62, 78)),
  ),
  parking: clampSetting("parking", randomInt(4, 16)),
  street: clampSetting("street", randomInt(46, 74)),
  alignment: clampSetting("alignment", randomInt(54, 86)),
  height: clampSetting("height", randomInt(48, 82)),
});

export function CityTwinApp() {
  const { resolvedTheme, setTheme } = useTheme();
  const handleRef = useRef<CityTwinHandle | null>(null);
  const autoAbortRef = useRef<AbortController | null>(null);
  const settingsRef = useRef<CityTwinSettings>(DEFAULT_SETTINGS);

  const [mounted, setMounted] = useState(false);
  const [settings, setSettings] = useState<CityTwinSettings>(DEFAULT_SETTINGS);
  const [allowWater, setAllowWater] = useState(false);
  const [autoMode, setAutoMode] = useState<AutoImprovementMode>("idle");
  const [controlsOpen, setControlsOpen] = useState(false);
  const [bottomSheetExpanded, setBottomSheetExpanded] = useState(false);
  const [progress, setProgress] = useState(8);
  const [status, setStatus] = useState("Booting the CityTwin engine…");
  const [pills, setPills] = useState<CityTwinPills>({
    roads: 0,
    water: 0,
    anchors: 0,
  });
  const [metrics, setMetrics] = useState<CityTwinMetrics | null>(null);
  const [population, setPopulation] = useState<CityTwinPopulation | null>(null);
  const [impact, setImpact] = useState<CityTwinImpact | null>(null);
  const [scenario, setScenario] = useState("No scenario yet");
  const [report, setReport] = useState("Loading the demo zone…");
  const [hint, setHint] = useState(
    "Click at least four points. Drag vertices to reshape.",
  );
  const autoRunning = autoMode !== "idle";

  const stopAutoImprovement = useCallback(
    (reason: "manual" | "stop" | "restart" | "unmount") => {
      autoAbortRef.current?.abort();
      autoAbortRef.current = null;
      const stopAutoOrbit = handleRef.current?.stopAutoOrbit;
      if (typeof stopAutoOrbit === "function") {
        stopAutoOrbit();
      }
      setAutoMode("idle");

      if (reason === "stop") {
        setProgress(96);
        setStatus("Auto improvement stopped. You can edit the scenario manually.");
        toast("Auto improvement stopped. You can edit the scenario manually.");
      }
    },
    [],
  );

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

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
        onImpact: setImpact,
        onScenario: setScenario,
        onReport: setReport,
        onHint: setHint,
        onPills: setPills,
        onToast: (text) => toast(text),
        onAutoInterrupted: () => stopAutoImprovement("manual"),
      });
      handleRef.current = handle;
    });

    return () => {
      cancelled = true;
      stopAutoImprovement("unmount");
      handleRef.current?.destroy();
      handleRef.current = null;
    };
  }, [stopAutoImprovement]);

  const isDark = mounted ? resolvedTheme === "dark" : false;

  const applySettingFromAuto = (key: CityTwinSettingKey, value: number) => {
    setSettings((prev) => {
      const next = { ...prev, [key]: clampSetting(key, value) };
      settingsRef.current = next;
      return next;
    });
    handleRef.current?.setSetting(key, clampSetting(key, value));
  };

  const applyAutoSettings = async (
    target: CityTwinSettings,
    signal: AbortSignal,
  ) => {
    const order: CityTwinSettingKey[] = [
      "green",
      "parking",
      "street",
      "alignment",
      "density",
      "height",
    ];

    for (const key of order) {
      const start = settingsRef.current[key];
      const end = target[key];
      const steps = 5;

      for (let step = 1; step <= steps; step += 1) {
        if (signal.aborted) {
          throw new DOMException("Aborted", "AbortError");
        }

        const value = Math.round(start + ((end - start) * step) / steps);
        applySettingFromAuto(key, value);
        await sleep(AUTO_TIMING.parameterStepMs, signal);
      }
    }
  };

  const startAutoImprovement = async () => {
    const handle = handleRef.current;
    if (!handle) {
      toast("Map is still loading. Try again in a moment.");
      return;
    }

    autoAbortRef.current?.abort();
    handle.stopAutoOrbit();

    const controller = new AbortController();
    autoAbortRef.current = controller;
    const signal = controller.signal;

    try {
      setAutoMode("overview");
      setControlsOpen(false);
      setBottomSheetExpanded(false);

      await handle.flyToLondonOverview({ signal });
      await sleep(AUTO_TIMING.pauseAfterOverviewMs, signal);

      setAutoMode("selecting");
      await handle.pickAutoImprovementZone({ signal, reveal: true });

      setAutoMode("waiting-initial-plan");
      let rendered = await handle.waitForPlanRender({
        signal,
        timeoutMs: AUTO_TIMING.waitForInitialPlanTimeoutMs,
        minGeneratedFeatures: 3,
      });

      if (!rendered) {
        setAutoMode("selecting");
        await handle.pickAutoImprovementZone({ signal, reveal: true });
        setAutoMode("waiting-initial-plan");
        rendered = await handle.waitForPlanRender({
          signal,
          timeoutMs: AUTO_TIMING.waitForInitialPlanTimeoutMs,
          minGeneratedFeatures: 3,
        });
      }

      setAutoMode("tuning");
      setControlsOpen(true);
      setBottomSheetExpanded(true);
      setAllowWater(false);
      handle.setAllowWater(false);

      const target = buildRandomGreenerSettings(settingsRef.current);
      await applyAutoSettings(target, signal);

      setAutoMode("waiting-improved-plan");
      handle.setSetting("green", settingsRef.current.green);
      await handle.waitForPlanRender({
        signal,
        timeoutMs: AUTO_TIMING.waitForImprovedPlanTimeoutMs,
        minGeneratedFeatures: rendered ? 3 : 1,
      });

      if (window.innerWidth < 768) {
        window.setTimeout(() => setBottomSheetExpanded(false), 2000);
      }

      setAutoMode("orbiting");
      handle.startAutoOrbit({ signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }

      console.error("Auto improvement failed", error);
      if (autoAbortRef.current === controller) {
        autoAbortRef.current = null;
        setAutoMode("idle");
      }
      handle.stopAutoOrbit();
      toast("Auto improvement failed. You can continue manually.");
    }
  };

  const restartAutoImprovement = () => {
    stopAutoImprovement("restart");
    void startAutoImprovement();
  };

  const handleSetting = (key: CityTwinSettingKey, value: number) => {
    stopAutoImprovement("manual");
    const nextValue = clampSetting(key, value);
    setSettings((prev) => {
      const next = { ...prev, [key]: nextValue };
      settingsRef.current = next;
      return next;
    });
    handleRef.current?.setSetting(key, nextValue);
  };

  const handleAllowWater = (on: boolean) => {
    stopAutoImprovement("manual");
    setAllowWater(on);
    handleRef.current?.setAllowWater(on);
  };

  const handleToggleTheme = (dark: boolean) => {
    stopAutoImprovement("manual");
    setTheme(dark ? "dark" : "light");
    handleRef.current?.setTheme(dark ? "dark" : "light");
  };

  const runManualAction = (action: () => void) => {
    stopAutoImprovement("manual");
    action();
  };

  const homeButton = (
    <div className="flex w-fit items-center justify-between gap-2 border-[0.5px] bg-card px-3 py-2 shadow-sm">
      <Button asChild size="sm" variant="ghost">
        <Link href="/" className="hover:bg-transparent">
          <ArrowLeftIcon data-icon="inline-start" />
          Home
        </Link>
      </Button>
    </div>
  );

  const controlsCard = (
    <ControlsCard
      settings={settings}
      allowWater={allowWater}
      isDark={isDark}
      autoRunning={autoRunning}
      autoMode={autoMode}
      controlsOpen={controlsOpen}
      onControlsOpenChange={setControlsOpen}
      onStartAutoImprovement={() => void startAutoImprovement()}
      onStopAutoImprovement={() => stopAutoImprovement("stop")}
      onRestartAutoImprovement={restartAutoImprovement}
      onSetting={handleSetting}
      onAllowWater={handleAllowWater}
      onToggleTheme={handleToggleTheme}
      onDemo={() => runManualAction(() => handleRef.current?.loadDemo())}
      onUndo={() => runManualAction(() => handleRef.current?.undo())}
      onClear={() => runManualAction(() => handleRef.current?.clearZone())}
      onFit={() => runManualAction(() => handleRef.current?.fit())}
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
          <Button
            size="sm"
            variant="destructive"
            onClick={() => stopAutoImprovement("stop")}
          >
            Stop
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={restartAutoImprovement}
          >
            Restart
          </Button>
        </div>
      ) : null}

      {/* Desktop: two floating columns. Hidden on mobile in favour of the sheet. */}
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

      {/* Mobile: a floating Home button + a single draggable bottom sheet. */}
      <div className="absolute left-3 top-3 z-30 md:hidden">{homeButton}</div>
      <BottomSheet
        expanded={bottomSheetExpanded}
        onExpandedChange={setBottomSheetExpanded}
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
