"use client";

import { useEffect, useState } from 'react';
import Header from './components/Header';
import { fetchInitData, InitData } from '@/lib/api';
import KHTable from './components/tabs/KHTable';
import MoneyTable from './components/tabs/MoneyTable';
import HistoryTable from './components/tabs/HistoryTable';
import PlayerModal from './components/modals/PlayerModal';
import ObserverModal from './components/modals/ObserverModal';

export default function Home() {
    const [initData, setInitData] = useState<InitData | null>(null);
    const [activeTab, setActiveTab] = useState("kh");
    const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
    const [observerTarget, setObserverTarget] = useState<{ roleId: number; name: string } | null>(null);

    useEffect(() => {
        fetchInitData()
            .then(setInitData)
            .catch((err) => console.error("Failed to fetch init data:", err));
    }, []);

    return (
        <main>
            <Header data={initData} activeTab={activeTab} onTabChange={setActiveTab} />

            <div className="container mt-4" style={{ minHeight: '100vh', padding: '20px' }}>
                {activeTab === 'kh' && (
                    <KHTable
                        onRowClick={setSelectedRoleId}
                        onObserverClick={(roleId, name) => setObserverTarget({ roleId, name })}
                        classes={initData?.classes}
                    />
                )}

                {activeTab === 'money' && (
                    <MoneyTable
                        onRowClick={setSelectedRoleId}
                        onObserverClick={(roleId, name) => setObserverTarget({ roleId, name })}
                        classes={initData?.classes}
                    />
                )}

                {activeTab === 'history' && (
                    <HistoryTable
                        onRowClick={setSelectedRoleId}
                        onObserverClick={(roleId, name) => setObserverTarget({ roleId, name })}
                        classes={initData?.classes}
                    />
                )}
            </div>

            {selectedRoleId && (
                <PlayerModal
                    roleId={selectedRoleId}
                    onClose={() => setSelectedRoleId(null)}
                    onSave={() => {
                        setSelectedRoleId(null);
                        window.location.reload();
                    }}
                />
            )}

            {observerTarget && (
                <ObserverModal
                    roleId={observerTarget.roleId}
                    nickname={observerTarget.name}
                    onClose={() => setObserverTarget(null)}
                />
            )}

            <footer className="footer-spider">
                <div className="spider-container">
                    <div className="spider-thread"></div>
                    <span className="spider-hanging-icon">🕷️</span>
                </div>
                <div className="footer-text-container">
                    <h2 className="footer-title">ARAHNIUS</h2>
                    <p className="footer-subtitle">We Weave the Fate.</p>
                </div>
            </footer>
        </main>
    );
}
