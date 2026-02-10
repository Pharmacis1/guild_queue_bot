/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    images: {
        unoptimized: true,
    },
    // rewrites is not compatible with output: 'export'
    // async rewrites() { ... } 
};

export default nextConfig;
