import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

export const metadata = {
  title: "UrbanFlux CityTwin",
  description: "Interactive London urban regeneration map demo.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body data-theme="dark">{children}</body>
    </html>
  );
}
