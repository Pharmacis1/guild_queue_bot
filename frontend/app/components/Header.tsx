"use client";

import React from 'react';
import { InitData } from '@/lib/api';

interface HeaderProps {
    data: InitData | null;
    activeTab: string;
    onTabChange: (tab: string) => void;
}

export default function Header({ data, activeTab, onTabChange }: HeaderProps) {
    const user = data?.user;
    const lastUpdated = data?.last_updated || "Loading...";

    return (
        <>
            {/* Thin Top Header */}
            <div className="thin-header">
                <div className="thin-header-content">
                    <div className="thin-header-left">
                        <span className="upd-text">Обновлено: {lastUpdated}</span>
                    </div>
                    <div className="thin-header-right">
                        {user ? (
                            <div className="guest-profile">
                                <img
                                    src={user.avatar_url || "/img/default_avatar.png"}
                                    alt="Avatar"
                                    className="guest-avatar"
                                />
                                <span className="guest-name">{user.username}</span>
                                {/* Logout logic would go here, maybe later */}
                            </div>
                        ) : (
                            <div className="guest-profile">
                                <img src="/img/spider_arcane_ruby_transparent.png" alt="Guest" className="guest-avatar" />
                                <span className="guest-name">Guest</span>
                                {/* Login Button logic will be added here */}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Hero Section */}
            <section className="hero-section">
                {/* Parallax Background Layers removed to match original */}

                <div className="hero-content">
                    <a href="#" className="spider-main-logo">
                        <img src="/img/spider_arcane_ruby_transparent.png" alt="Arahnius Spider" className="spider-main-logo-img" />
                    </a>
                    <h1 className="hero-title">We Weave the Fate</h1>
                    <div className="hero-subtitle">Arahnius Clan</div>
                </div>
            </section>

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
                    </div>
                </div>
            </nav>
        </>
    );
}
