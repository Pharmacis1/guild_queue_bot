import './globals.css'
import type { Metadata, Viewport } from 'next'
import SpiderScroll from './components/ui/SpiderScroll'
import Script from 'next/script'

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
                <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
                {process.env.NODE_ENV === 'production' && (
                    <>
                        {/* Google Analytics */}
                        <script
                            async
                            src="https://www.googletagmanager.com/gtag/js?id=G-KN1NQWDJFW"
                        />
                        <script
                            dangerouslySetInnerHTML={{
                                __html: `
                                    window.dataLayer = window.dataLayer || [];
                                    function gtag(){dataLayer.push(arguments);}
                                    gtag('js', new Date());
                                    gtag('config', 'G-KN1NQWDJFW');
                                `,
                            }}
                        />

                        {/* Yandex Metrica */}
                        <script
                            dangerouslySetInnerHTML={{
                                __html: `
                                   (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
                                   m[i].l=1*new Date();
                                   for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
                                   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
                                   (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

                                   ym(108543154, "init", {
                                        clickmap:true,
                                        trackLinks:true,
                                        accurateTrackBounce:true,
                                        webvisor:true
                                   });
                                `,
                            }}
                        />
                    </>
                )}
            </head>
            <body>
                {process.env.NODE_ENV === 'production' && (
                    <noscript>
                        <div>
                            <img
                                src="https://mc.yandex.ru/watch/108543154"
                                style={{ position: 'absolute', left: '-9999px' }}
                                alt=""
                            />
                        </div>
                    </noscript>
                )}
                {children}
                <SpiderScroll />
            </body>
        </html>
    )
}
