import React, { useEffect, useRef } from 'react';
import api from '@/lib/api';

interface TelegramLoginWidgetProps {
    botName: string;
    authUrl: string; // Kept for interface compatibility but we'll ignore it for onauth
}

const TelegramLoginWidget: React.FC<TelegramLoginWidgetProps> = ({ botName }) => {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!botName) return;

        // Define global callback
        (window as any).onTelegramAuth = async (user: any) => {
            // console.log("Telegram Auth User:", user);
            try {
                const response = await api.post('/login/widget', user);
                if (response.data.status === 'ok') {
                    window.location.reload();
                } else {
                    alert('Ошибка входа: ' + (response.data.message || 'Unknown error'));
                }
            } catch (error: any) {
                console.error("Login widget error:", error);
                const msg = error.response?.data?.message || error.message;
                alert('Ошибка авторизации: ' + msg);
            }
        };

        const script = document.createElement('script');
        script.src = "https://telegram.org/js/telegram-widget.js?22";
        script.setAttribute('data-telegram-login', botName);
        script.setAttribute('data-size', 'medium');
        script.setAttribute('data-radius', '5');
        // Use onauth instead of auth-url
        script.setAttribute('data-onauth', 'onTelegramAuth(user)');
        script.setAttribute('data-request-access', 'write');
        script.async = true;

        if (containerRef.current) {
            containerRef.current.innerHTML = ''; // Clear previous if any
            containerRef.current.appendChild(script);
        }

        // Cleanup
        return () => {
            // We can't really remove the global function easily without risking race conditions if component remounts fast,
            // but for this simple app it's fine.
            // delete (window as any).onTelegramAuth;
        };
    }, [botName]);

    return <div ref={containerRef}></div>;
};

export default TelegramLoginWidget;
