'use client';

import React from 'react';
import { usePathname } from 'next/navigation';

const MobileStub: React.FC = () => {
    const pathname = usePathname();
    
    // Hide stub for Player Profile (TMA) routes
    if (pathname?.startsWith('/player/')) {
        return null;
    }

    return (
        <div className="mobile-stub">
            <div className="mobile-stub-content">
                <img
                    src="/img/spider_arcane_ruby_transparent.png"
                    alt="Spider Logo"
                    className="mobile-stub-logo"
                />
                <h2 className="mobile-stub-title">
                    Мобильная<br />версия<br />недоступна
                </h2>
                <p className="mobile-stub-text">
                    Мобильная версия сайта<br />
                    пока недоступна.<br />
                    Пожалуйста, зайдите с<br />
                    компьютера.
                </p>
            </div>
        </div>
    );
};

export default MobileStub;
