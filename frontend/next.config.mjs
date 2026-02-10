/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    images: {
        unoptimized: true,
    },
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: 'http://bot:8081/api/:path*',
            },
            {
                source: '/admin/:path*',
                destination: 'http://bot:8081/admin/:path*',
            },
            {
                source: '/static/:path*',
                destination: 'http://bot:8081/static/:path*',
            },
        ];
    },
};

export default nextConfig;
