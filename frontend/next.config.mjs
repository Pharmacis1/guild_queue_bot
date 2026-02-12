/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    images: {
        unoptimized: true,
    },
    // rewrites is not compatible with output: 'export'
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: 'http://127.0.0.1:8081/api/:path*',
            },
        ];
    },
};

export default nextConfig;
