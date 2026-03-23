import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { InitData, logout } from '@/lib/api';
import TelegramLoginWidget from './TelegramLoginWidget';

interface HeaderProps {
    data: InitData | null;
    activeTab: string;
    onTabChange: (tab: string) => void;
}

export default function Header({ data, activeTab, onTabChange }: HeaderProps) {
    const user = data?.user;
    const lastUpdated = data?.last_updated || "Загрузка...";
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [isCollapsed, setIsCollapsed] = useState(false);
    const menuRef = useRef<HTMLDivElement>(null);

    // Persistence for collapsed state
    useEffect(() => {
        const saved = localStorage.getItem('header_collapsed');
        if (saved === 'true') setIsCollapsed(true);
    }, []);

    const toggleCollapse = () => {
        const newState = !isCollapsed;
        setIsCollapsed(newState);
        localStorage.setItem('header_collapsed', newState ? 'true' : 'false');
    };

    // Close menu when clicking outside
    // Close menu when clicking outside - DISABLED per user request
    // useEffect(() => {
    //     function handleClickOutside(event: MouseEvent) {
    //         if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
    //             setIsMenuOpen(false);
    //         }
    //     }
    //     document.addEventListener("mousedown", handleClickOutside);
    //     return () => {
    //         document.removeEventListener("mousedown", handleClickOutside);
    //     };
    // }, []);

    const [mounted, setMounted] = useState(false);
    useEffect(() => {
        setMounted(true);
        return () => setMounted(false);
    }, []);

    // Check for auth errors in URL
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const error = params.get('error');
        if (error) {
            if (error === 'not_registered') {
                alert("Ошибка: Вы не зарегистрированы в боте. Пожалуйста, напишите /start боту.");
            } else if (error === 'auth_failed') {
                alert("Ошибка: Авторизация не удалась.");
            } else {
                alert(`Ошибка входа: ${error}`);
            }
            // Clean URL
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }, []);




    const modalContent = (
        <div
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                width: '100vw',
                height: '100vh',
                backgroundColor: 'rgba(0, 0, 0, 0.85)',
                zIndex: 99999,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                backdropFilter: 'blur(8px)'
            }}
        // onClick={() => setIsMenuOpen(false)} // Disabled close on background click per user request
        >
            <div
                onClick={(e) => e.stopPropagation()} // Prevent close when clicking content
                style={{
                    width: '90%',
                    maxWidth: '400px',
                    backgroundColor: '#0a0a0a',
                    border: '1px solid #333',
                    borderRadius: '16px',
                    padding: '30px',
                    boxShadow: '0 0 30px rgba(209, 0, 31, 0.15)', // Subtle ruby glow
                    position: 'relative',
                    color: '#fff',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px'
                }}
            >
                {/* Close Button */}
                <button
                    onClick={() => setIsMenuOpen(false)}
                    style={{
                        position: 'absolute',
                        top: '15px',
                        right: '20px',
                        background: 'transparent',
                        border: 'none',
                        color: '#666',
                        fontSize: '1.5rem',
                        cursor: 'pointer',
                        lineHeight: 1
                    }}
                >
                    ✕
                </button>

                {/* Modal Title */}
                <h5 style={{
                    margin: 0,
                    textAlign: 'center',
                    fontSize: '1.5rem',
                    fontFamily: "'Cinzel', serif",
                    borderBottom: '1px solid #333',
                    paddingBottom: '15px',
                    color: '#E0E0E0'
                }}>
                    Меню
                </h5>

                {/* Modal Content */}
                <div style={{ textAlign: 'center' }}>
                    {user ? (
                        <>
                            <div style={{ marginBottom: '20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
                                <img
                                    src={user.avatar_url || "/img/spider_arcane_ruby_transparent.png"}
                                    alt="Avatar"
                                    style={{ width: '80px', height: '80px', borderRadius: '50%', border: '2px solid #8B0000' }}
                                />
                                <div style={{ color: '#ccc' }}>
                                    Вы вошли как <br />
                                    <span style={{ color: '#fff', fontWeight: 'bold', fontSize: '1.2rem' }}>{user.username}</span>
                                </div>
                            </div>

                            <a
                                className="btn btn-danger w-100"
                                href="/logout"
                                style={{
                                    display: 'block',
                                    textDecoration: 'none',
                                    textAlign: 'center',
                                    width: '100%',
                                    padding: '12px',
                                    borderRadius: '6px',
                                    background: 'linear-gradient(45deg, #8B0000, #b30000)',
                                    border: '1px solid #ff4d6d',
                                    color: 'white',
                                    fontWeight: 'bold',
                                    cursor: 'pointer',
                                    textTransform: 'uppercase',
                                    letterSpacing: '1px'
                                }}
                            >
                                Выйти
                            </a>
                        </>
                    ) : (
                        <>
                            <div style={{ marginBottom: '20px', color: '#ccc', fontSize: '1.1rem' }}>Авторизация</div>
                            {data?.bot_username && (
                                <div style={{ display: 'flex', justifyContent: 'center', transform: 'scale(1.2)', margin: '15px 0' }}>
                                    <TelegramLoginWidget
                                        botName={data.bot_username}
                                        authUrl="/login/telegram"
                                    />
                                </div>
                            )}
                            <p style={{ marginTop: '20px', fontSize: '0.8rem', color: '#666' }}>
                                Нажмите кнопку выше, чтобы войти через Telegram.
                            </p>
                        </>
                    )}
                </div>
            </div>
        </div>
    );

    return (
        <>
            {/* Thin Top Header */}
            <div className="thin-header">
                <div className="thin-header-content">
                    <div className="thin-header-left" style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                        <button 
                            onClick={toggleCollapse}
                            style={{
                                background: 'transparent',
                                border: '1px solid rgba(255, 255, 255, 0.2)',
                                color: '#ccc',
                                cursor: 'pointer',
                                borderRadius: '4px',
                                padding: '2px 8px',
                                fontSize: '0.8rem',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '5px',
                                transition: 'all 0.2s'
                            }}
                            title={isCollapsed ? "Раскрыть заголовок" : "Свернуть заголовок"}
                        >
                            {isCollapsed ? '▼' : '▲'} 
                            <span style={{ fontSize: '0.7rem', opacity: 0.8 }}>{isCollapsed ? 'LOGO' : 'HIDE'}</span>
                        </button>
                        <span className="upd-text">Обновлено: {lastUpdated}</span>
                    </div>
                    <div className="thin-header-right" style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: '15px' }} ref={menuRef}>
                        <div
                            className="guest-profile"
                            style={{ gap: '10px', cursor: 'pointer' }}
                            onClick={() => setIsMenuOpen(!isMenuOpen)}
                        >
                            <img
                                src={user?.avatar_url || "/img/spider_arcane_ruby_transparent.png"}
                                alt="Avatar"
                                className="guest-avatar"
                            />
                            <span className="guest-name">{user?.username || "Гость"}</span>
                            <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>▼</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Hero Section - Toggleable */}
            {!isCollapsed && (
                <section className="hero-section">
                    <div className="hero-content">
                        <a href="#" className="spider-main-logo">
                            <img src="/img/spider_arcane_ruby_transparent.png" alt="Arahnius Spider" className="spider-main-logo-img" />
                        </a>
                        <h1 className="hero-title">We Weave the Fate</h1>
                        <div className="hero-subtitle">Arahnius Clan</div>
                    </div>
                </section>
            )}

            {/* Navigation Tabs (Sticky) */}
            <nav className="top-nav">
                <div style={{ display: 'flex', justifyContent: 'center', position: 'relative', height: '50px' }}>
                    <div className="header-tabs">
                        <button
                            className={`header-tab ${activeTab === 'kh' ? 'active' : ''}`}
                            onClick={() => onTabChange('kh')}
                        >
                            КХ этапы
                        </button>
                        <button
                            className={`header-tab ${activeTab === 'money' ? 'active' : ''}`}
                            onClick={() => onTabChange('money')}
                        >
                            Доблесть
                        </button>
                        <button
                            className={`header-tab ${activeTab === 'history' ? 'active' : ''}`}
                            onClick={() => onTabChange('history')}
                        >
                            История
                        </button>
                        {user?.is_master && (
                            <button
                                className={`header-tab ${activeTab === 'master' ? 'active' : ''}`}
                                onClick={() => onTabChange('master')}
                            >
                                Панель мастера
                            </button>
                        )}
                    </div>
                </div>
            </nav>

            {/* Menu Modal Rendered via Portal */}
            {mounted && isMenuOpen && createPortal(modalContent, document.body)}
        </>
    );
}
