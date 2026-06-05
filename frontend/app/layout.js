import "./globals.css";

export const metadata = {
  title: "UrbanFlux",
  description: "Hello World demo consuming FastAPI",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
