"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { toast } from "sonner";
import { sleep } from "@/lib/abortable";
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
import { CityTwinLayout } from "./CityTwinLayout";
import {
  AUTO_TIMING,
  DEFAULT_SETTINGS,
  buildRandomGreenerSettings,
  clampSetting,
} from "./settings";
import { useCityTwinMapLifecycle } from "./useCityTwinMapLifecycle";

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

  useCityTwinMapLifecycle({
    handleRef,
    initialSettings: DEFAULT_SETTINGS,
    stopAutoImprovement,
    setProgress,
    setStatus,
    setMetrics,
    setPopulation,
    setImpact,
    setScenario,
    setReport,
    setHint,
    setPills,
  });

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
        allowExisting: true,
      });

      if (!rendered) {
        setProgress(30);
        setStatus("Trying another neighbourhood with richer map context...");
        setAutoMode("selecting");
        await handle.pickAutoImprovementZone({ signal, reveal: true });
        setAutoMode("waiting-initial-plan");
        rendered = await handle.waitForPlanRender({
          signal,
          timeoutMs: AUTO_TIMING.waitForInitialPlanTimeoutMs,
          minGeneratedFeatures: 3,
          allowExisting: true,
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

  return (
    <CityTwinLayout
      isDark={isDark}
      settings={settings}
      allowWater={allowWater}
      autoRunning={autoRunning}
      autoMode={autoMode}
      controlsOpen={controlsOpen}
      bottomSheetExpanded={bottomSheetExpanded}
      progress={progress}
      status={status}
      pills={pills}
      metrics={metrics}
      population={population}
      impact={impact}
      scenario={scenario}
      report={report}
      hint={hint}
      onControlsOpenChange={setControlsOpen}
      onBottomSheetExpandedChange={setBottomSheetExpanded}
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
}
