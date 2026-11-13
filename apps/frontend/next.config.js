/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  experimental: {
    // Compile only the icon/chart modules each page actually imports. This
    // keeps dev builds fast instead of pulling whole barrels into every route.
    optimizePackageImports: ["lucide-react", "framer-motion", "recharts"],
  },

  images: {
    formats: ["image/avif", "image/webp"],
  },

  async redirects() {
    return [
      { source: "/app/super-admin", destination: "/system-owner/dashboard", permanent: false },
      { source: "/app/super-admin/organizations", destination: "/system-owner/organizations", permanent: false },
      { source: "/app/super-admin/plans", destination: "/system-owner/plans", permanent: false },
      { source: "/app/super-admin/cms", destination: "/system-owner/cms", permanent: false },
      { source: "/app/super-admin/billing", destination: "/system-owner/payments", permanent: false },
      { source: "/app/super-admin/monitoring", destination: "/system-owner/dashboard", permanent: false },
      { source: "/app/super-admin/abuse", destination: "/system-owner/organizations", permanent: false },
    ];
  },
};

module.exports = nextConfig;
