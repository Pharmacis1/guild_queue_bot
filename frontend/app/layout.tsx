import './globals.css'
import type { Metadata } from 'next'
import SpiderScroll from './components/ui/SpiderScroll'

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
            </head>
            <body>
                {children}
                <SpiderScroll />
            </body>
        </html>
    )
}
