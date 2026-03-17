import './globals.css'
import type { Metadata, Viewport } from 'next'
import SpiderScroll from './components/ui/SpiderScroll'
import MobileStub from './components/MobileStub'

export const viewport: Viewport = {
    width: 'device-width',
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
}

export const metadata: Metadata = {
    title: 'Arahnius Clan',
    description: 'Guild Queue Bot Dashboard',
}

export default function RootLayout({
    children,
}: {
    children: React.ReactNode
}) {
    return (
        <html lang="ru">
            <head>
                <link rel="icon" type="image/png" href="/img/spider_arcane_ruby_transparent.png" />
                <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Montserrat:wght@300;400;600&family=Rajdhani:wght@500;600;700&family=Cormorant+Garamond:wght@500;600;700&display=swap" rel="stylesheet" />
                <link href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css" rel="stylesheet" />
            </head>
            <body>
                <MobileStub />
                {children}
                <SpiderScroll />
            </body>
        </html>
    )
}
