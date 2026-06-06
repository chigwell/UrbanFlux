"use client";

import { MoonIcon, RotateCcwIcon, SunIcon, Trash2Icon, Undo2Icon, MapPinnedIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import type { CityTwinSettingKey, CityTwinSettings } from "@/lib/cityTwinMap";
import { CollapsiblePanel } from "./CollapsiblePanel";

const SLIDERS: {
  key: CityTwinSettingKey;
  label: string;
  min: number;
  max: number;
  hint: string;
}[] = [
  { key: "density", label: "Housing density", min: 5, max: 100, hint: "Homes per built block" },
  { key: "green", label: "Green space target", min: 5, max: 80, hint: "Share reserved as parks" },
  { key: "parking", label: "Parking pressure", min: 0, max: 80, hint: "Surface parking demand" },
  { key: "street", label: "Road fill", min: 0, max: 100, hint: "Boundary anchors connected" },
  { key: "alignment", label: "Road alignment", min: 0, max: 100, hint: "How straight corridors run" },
  { key: "height", label: "Height ambition", min: 0, max: 100, hint: "Massing of tall buildings" },
];

interface ControlsCardProps {
  settings: CityTwinSettings;
  allowWater: boolean;
  isDark: boolean;
  onSetting: (key: CityTwinSettingKey, value: number) => void;
  onAllowWater: (on: boolean) => void;
  onToggleTheme: (dark: boolean) => void;
  onDemo: () => void;
  onUndo: () => void;
  onClear: () => void;
  onFit: () => void;
}

export function ControlsCard({
  settings,
  allowWater,
  isDark,
  onSetting,
  onAllowWater,
  onToggleTheme,
  onDemo,
  onUndo,
  onClear,
  onFit,
}: ControlsCardProps) {
  return (
    <CollapsiblePanel title="Urban controls" meta="Scenario">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-2">
          <Button size="sm" onClick={onDemo} className="rounded-none p-4">
            <MapPinnedIcon data-icon="inline-start"  />
            Demo
          </Button>
          <Button size="sm" variant="outline" onClick={onUndo} className="rounded-none p-4">
            <Undo2Icon data-icon="inline-start" />
            Undo
          </Button>
          <Button size="sm" variant="outline" onClick={onClear} className="rounded-none p-4">
            <Trash2Icon data-icon="inline-start" />
            Clear
          </Button>
          <Button size="sm" variant="outline" onClick={onFit} className="rounded-none p-4">
            <RotateCcwIcon data-icon="inline-start" />
            Refit
          </Button>
        </div>

        <Separator />

        <div className="flex flex-col gap-3">
          <label className="flex items-center justify-between gap-3 text-sm">
            <span className="flex items-center gap-2 font-medium">
              {isDark ? <MoonIcon className="size-4" /> : <SunIcon className="size-4" />}
              {isDark ? "Dark" : "Light"} basemap
            </span>
            <Switch checked={isDark} onCheckedChange={onToggleTheme} aria-label="Toggle basemap theme" />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">
              Water override
              <span className="block text-xs font-normal text-muted-foreground">
                Allow building over rivers
              </span>
            </span>
            <Switch
              checked={allowWater}
              onCheckedChange={onAllowWater}
              aria-label="Toggle water override"
            />
          </label>
        </div>

        <Separator />

        <div className="flex flex-col gap-4">
          {SLIDERS.map((slider) => (
            <div key={slider.key} className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{slider.label}</span>
                <span className="text-sm tabular-nums text-muted-foreground">
                  {settings[slider.key]}
                </span>
              </div>
              <Slider
                value={[settings[slider.key]]}
                min={slider.min}
                max={slider.max}
                step={1}
                onValueChange={([value]) => onSetting(slider.key, value)}
                aria-label={slider.label}
              />
              <span className="text-xs text-muted-foreground">{slider.hint}</span>
            </div>
          ))}
        </div>
      </div>
    </CollapsiblePanel>
  );
}
