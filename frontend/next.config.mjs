/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
