"use client";

import { useEffect, useState } from 'react';
import Header from './components/Header';
import { fetchInitData, InitData } from '@/lib/api';
import KHTable from './components/tabs/KHTable';
import MoneyTable from './components/tabs/MoneyTable';
import HistoryTable from './components/tabs/HistoryTable';
import PlayerModal from './components/modals/PlayerModal';

export default function Home() {
    const [initData, setInitData] = useState<InitData | null>(null);
    const [activeTab, setActiveTab] = useState("kh");
    const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);

    useEffect(() => {
        fetchInitData()
            .then(setInitData)
            .catch((err) => console.error("Failed to fetch init data:", err));
    }, []);

    return (
        <main>
            <Header data={initData} activeTab={activeTab} onTabChange={setActiveTab} />

            <div className="container mt-4" style={{ minHeight: '100vh', padding: '20px' }}>
                {activeTab === 'kh' && <KHTable onRowClick={setSelectedRoleId} />}

                {activeTab === 'money' && <MoneyTable />}

                {activeTab === 'history' && <HistoryTable />}
            </div>

            {selectedRoleId && (
                <PlayerModal
                    roleId={selectedRoleId}
                    onClose={() => setSelectedRoleId(null)}
                    onSave={() => {
                        // Ideally refresh table data here
                        setSelectedRoleId(null);
                        window.location.reload(); // Simple refresh for now
                    }}
                />
            )}

            <footer className="footer-spider">
                <div className="spider-hanging">🕷️</div>
                <p className="text-muted small">© 2024 Arahnius Clan. All rights reserved.</p>
            </footer>
        </main>
    );
}
