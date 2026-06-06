import {
  Building2Icon,
  GaugeIcon,
  LayersIcon,
  MousePointerClickIcon,
  RouteIcon,
  WavesIcon,
} from "lucide-react";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const FEATURES = [
  {
    icon: MousePointerClickIcon,
    title: "Draw any boundary",
    description:
      "Click points to outline a zone, then drag vertices and add midpoints. The plan replans on every edit.",
  },
  {
    icon: LayersIcon,
    title: "Real urban context",
    description:
      "Roads, water, buildings and parks are pulled live from vector tiles and the raw OpenStreetMap graph.",
  },
  {
    icon: RouteIcon,
    title: "Roads that connect",
    description:
      "Generated corridors snap to existing streets at boundary anchors instead of floating on a blank grid.",
  },
  {
    icon: WavesIcon,
    title: "Water-aware by default",
    description:
      "Rivers and basins act as hard masks. The generator refuses to guess across water unless you override it.",
  },
  {
    icon: Building2Icon,
    title: "Massing & green space",
    description:
      "Tune density, height, parking and green targets — buildings extrude in 3D as the scenario updates.",
  },
  {
    icon: GaugeIcon,
    title: "Live impact metrics",
    description:
      "Area, homes, road links, parking and protected water update instantly with a plain-language summary.",
  },
];

export function FeatureGrid() {
  return (
    <section id="features" className="mx-auto w-full max-w-6xl px-6 py-16 lg:py-24">
      <div className="mx-auto mb-12 max-w-2xl text-center">
        <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          A digital twin that reasons about the real city
        </h2>
        <p className="mt-4 text-lg text-muted-foreground text-pretty">
          Everything is generated from live geospatial data — no static
          screenshots, no pre-baked scenarios.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((feature) => (
          <Card key={feature.title} className="h-full">
            <CardHeader>
              <span className="mb-2 grid size-10 place-items-center rounded-lg bg-secondary text-secondary-foreground">
                <feature.icon className="size-5" />
              </span>
              <CardTitle>{feature.title}</CardTitle>
              <CardDescription className="text-pretty">
                {feature.description}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </section>
  );
}
