"use client";

import { useEffect, useState, useMemo } from 'react';
import Header from './components/Header';
import { fetchInitData, InitData, loginViaTMA } from '@/lib/api';
import { useRouter } from 'next/navigation';
import KHTable from './components/tabs/KHTable';
import MoneyTable from './components/tabs/MoneyTable';
import HistoryTable from './components/tabs/HistoryTable';
import PlayerModal from './components/modals/PlayerModal';
import ObserverModal from './components/modals/ObserverModal';
import SettingsModal from './components/modals/SettingsModal';
import MasterPanel from './components/tabs/MasterPanel';

export default function Home() {
    const [initData, setInitData] = useState<InitData | null>(null);
    const [activeTab, setActiveTab] = useState("kh");
    const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const [observerTarget, setObserverTarget] = useState<{ roleId: number; name: string } | null>(null);
    const [isTMA, setIsTMA] = useState<boolean | null>(null); // null means "detecting"
    const [loading, setLoading] = useState(true);

    const router = useRouter();

    useEffect(() => {
        const init = async () => {
            const tmaData = typeof window !== 'undefined' && (window as any).Telegram?.WebApp?.initData;
            const tmaActive = !!tmaData;
            setIsTMA(tmaActive);
            
            console.log("TMA Detection:", tmaActive);

            try {
                let data = await fetchInitData();
                console.log("Initial data loaded. User:", data.user?.username, "Main Role:", data.user?.main_role_id);
                
                // Auto-login if in TMA
                if (!data.user && tmaData) {
                    try {
                        console.log("Attempting TMA login...");
                        await loginViaTMA(tmaData);
                        data = await fetchInitData();
                        console.log("Data after TMA login. User:", data.user?.username);
                    } catch (e) {
                         console.error("Auto-login failed:", e);
                    }
                }
                
                setInitData(data);
                
                // Redirect to main character profile if available (TMA ONLY)
                if (data.user?.main_role_id && tmaActive) {
                    console.log("Redirecting to profile:", data.user.main_role_id);
                    router.replace(`/player/${data.user.main_role_id}`);
                }
            } catch (err) {
                console.error("Failed to fetch init data:", err);
            } finally {
                setLoading(false);
            }
        };
        init();
    }, [router]);

    const [refreshKey, setRefreshKey] = useState(0);
    const handleRefresh = () => setRefreshKey(prev => prev + 1);
 
    // Show loading while we are detecting environment or fetching data
    if (loading || isTMA === null) {
        return (
            <main style={{ background: '#0a0a0f', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ color: '#8B0000', textAlign: 'center' }}>
                    <div className="spinner-border" role="status" style={{ width: '3rem', height: '3rem' }}></div>
                    <div style={{ marginTop: '15px', fontFamily: 'Cinzel, serif', fontSize: '1.2rem' }}>Загрузка...</div>
                </div>
            </main>
        );
    }

    if (isTMA && (!initData?.user || !initData.user.main_role_id)) {
        const isRegistered = !!initData?.user;
        return (
            <main style={{ background: '#0a0a0f', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
                <div style={{
                    background: 'linear-gradient(145deg, #1a1a24, #0f0f16)',
                    border: '1px solid #8B0000',
                    borderRadius: '16px',
                    padding: '30px',
                    maxWidth: '400px',
                    width: '100%',
                    textAlign: 'center',
                    boxShadow: '0 10px 30px rgba(0,0,0,0.5)'
                }}>
                    <div style={{ fontSize: '50px', marginBottom: '20px' }}>🕷️</div>
                    <h2 style={{ color: '#fff', fontFamily: 'Cinzel, serif', marginBottom: '15px' }}>
                        {isRegistered ? 'Персонаж не привязан' : 'Добро пожаловать'}
                    </h2>
                    <p style={{ color: '#ccc', fontSize: '16px', lineHeight: '1.5', marginBottom: '25px' }}>
                        {isRegistered 
                            ? 'Ваш аккаунт зарегистрирован, но у вас еще нет привязанных персонажей. Пожалуйста, добавьте их в боте.'
                            : 'Для доступа к функциям гильдии в Telegram вам необходимо зарегистрироваться и привязать персонажа через бота.'}
                    </p>
                    <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: '8px', padding: '15px', textAlign: 'left', marginBottom: '25px' }}>
                        <div style={{ color: '#8B0000', fontWeight: 'bold', marginBottom: '8px' }}>Что делать:</div>
                        <ol style={{ color: '#aaa', fontSize: '14px', paddingLeft: '20px', margin: 0 }}>
                            {isRegistered ? (
                                <>
                                    <li>Вернитесь в чат с ботом</li>
                                    <li>Нажмите кнопку <b>«👥 Мои персонажи»</b></li>
                                    <li>Добавьте своих персонажей</li>
                                </>
                            ) : (
                                <>
                                    <li>Нажмите <b>/start</b> в боте</li>
                                    <li>Пришлите скриншот характеристик</li>
                                    <li>Дождитесь одобрения Мастера</li>
                                </>
                            )}
                        </ol>
                    </div>
                    <p style={{ color: '#666', fontSize: '12px', fontStyle: 'italic' }}>
                        {isRegistered 
                            ? 'После привязки персонажа, обновите это окно.'
                            : 'Если вы уже отправили данные, подождите, пока Мастер подтвердит вашу заявку.'}
                    </p>
                </div>
            </main>
        );
    }

    return (
        <main>
            <Header 
                data={initData} 
                activeTab={activeTab} 
                onTabChange={setActiveTab} 
                onSettingsOpen={() => setIsSettingsOpen(true)}
            />

            <div className="container mt-4" style={{ minHeight: '100vh', padding: '20px' }}>
                {activeTab === 'kh' && (
                    <KHTable
                        key={`kh-${refreshKey}`}
                        onRowClick={setSelectedRoleId}
                        onObserverClick={(roleId, name) => setObserverTarget({ roleId, name })}
                        classes={initData?.classes}
                        currentUser={initData?.user}
                    />
                )}

                {activeTab === 'money' && (
                    <MoneyTable
                        key={`money-${refreshKey}`}
                        onRowClick={setSelectedRoleId}
                        onObserverClick={(roleId, name) => setObserverTarget({ roleId, name })}
                        classes={initData?.classes}
                        currentUser={initData?.user}
                    />
                )}

                {activeTab === 'history' && (
                    <HistoryTable
                        key={`history-${refreshKey}`}
                        onRowClick={setSelectedRoleId}
                        onObserverClick={(roleId, name) => setObserverTarget({ roleId, name })}
                        classes={initData?.classes}
                        currentUser={initData?.user}
                    />
                )}

                {activeTab === 'master' && initData?.user?.is_master && (
                    <MasterPanel 
                        currentUser={initData?.user} 
                    />
                )}
            </div>

            {isSettingsOpen && (
                <SettingsModal
                    data={initData}
                    onClose={() => setIsSettingsOpen(false)}
                    onRefresh={handleRefresh}
                />
            )}

            {selectedRoleId && (
                <PlayerModal
                    roleId={selectedRoleId}
                    onClose={() => {
                        setSelectedRoleId(null);
                    }}
                    onSave={() => {
                        handleRefresh();
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
