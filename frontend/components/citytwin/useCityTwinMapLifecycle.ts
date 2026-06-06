"use client";

import { useEffect } from "react";
import type { RefObject } from "react";
import { toast } from "sonner";
import type {
  CityTwinHandle,
  CityTwinImpact,
  CityTwinMetrics,
  CityTwinPills,
  CityTwinPopulation,
  CityTwinSettings,
} from "@/lib/cityTwinMap";

interface CityTwinMapLifecycleOptions {
  handleRef: RefObject<CityTwinHandle | null>;
  initialSettings: CityTwinSettings;
  stopAutoImprovement: (reason: "manual" | "stop" | "restart" | "unmount") => void;
  setProgress: (value: number) => void;
  setStatus: (value: string) => void;
  setMetrics: (value: CityTwinMetrics | null) => void;
  setPopulation: (value: CityTwinPopulation | null) => void;
  setImpact: (value: CityTwinImpact | null) => void;
  setScenario: (value: string) => void;
  setReport: (value: string) => void;
  setHint: (value: string) => void;
  setPills: (value: CityTwinPills) => void;
}

export function useCityTwinMapLifecycle({
  handleRef,
  initialSettings,
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
}: CityTwinMapLifecycleOptions) {
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
        initialSettings,
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
  }, [
    handleRef,
    initialSettings,
    setHint,
    setImpact,
    setMetrics,
    setPills,
    setPopulation,
    setProgress,
    setReport,
    setScenario,
    setStatus,
    stopAutoImprovement,
  ]);
}
