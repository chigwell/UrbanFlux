const STEPS = [
  {
    step: "01",
    title: "Draw the zone",
    description:
      "Outline any area of London with four or more points. Reshape it live by dragging vertices and midpoints.",
  },
  {
    step: "02",
    title: "Read the context",
    description:
      "UrbanFlux fetches surrounding roads, rivers, buildings and parks from vector tiles and OpenStreetMap.",
  },
  {
    step: "03",
    title: "Generate the plan",
    description:
      "Connected roads, massed buildings, green space and impact metrics appear — and update as you tune controls.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="border-y bg-muted/30">
      <div className="mx-auto w-full max-w-6xl px-6 py-16 lg:py-24">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            From boundary to plan in three steps
          </h2>
        </div>
        <ol className="grid gap-8 md:grid-cols-3">
          {STEPS.map((item) => (
            <li key={item.step} className="flex flex-col gap-3">
              <span className="text-4xl font-semibold tabular-nums text-muted-foreground/40">
                {item.step}
              </span>
              <h3 className="text-xl font-semibold">{item.title}</h3>
              <p className="text-muted-foreground text-pretty">{item.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
