import { useState } from 'react';
import { UserData } from '@/lib/api';
import RewardDistribution from './RewardDistribution';

interface MasterPanelProps {
    currentUser?: UserData | null;
}

export default function MasterPanel({ currentUser }: MasterPanelProps) {
    const [activeSection, setActiveSection] = useState<'hub' | 'users' | 'rewards' | 'announce'>('hub');

    if (!currentUser?.is_master) {
        return (
            <div className="table-wrapper glow-border" style={{ textAlign: 'center', padding: '50px', marginTop: '20px' }}>
                <h2 style={{ color: '#ff4d4d' }}>Доступ запрещен</h2>
                <p style={{ color: '#ccc' }}>Эта панель доступна только Мастерам гильдии.</p>
            </div>
        );
    }

    if (activeSection === 'rewards') {
        return (
            <div className="table-wrapper glow-border" style={{ marginTop: '20px', padding: '30px' }}>
                <RewardDistribution currentUser={currentUser} onBack={() => setActiveSection('hub')} />
            </div>
        );
    }

    return (
        <div className="table-wrapper glow-border" style={{ marginTop: '20px', padding: '30px' }}>
            <div style={{ borderBottom: '1px solid #333', paddingBottom: '20px', marginBottom: '30px', textAlign: 'center' }}>
                <h1 style={{ fontFamily: "'Cinzel', serif", color: '#E0E0E0', margin: 0 }}>
                    👑 Панель Мастера
                </h1>
                <p style={{ color: '#aaa', marginTop: '10px' }}>
                    Центр управления функционалом бота
                </p>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '20px', justifyContent: 'center' }}>
                {/* Placeholder Cards for future features */}
                
                <div style={{ 
                    flex: '1 1 300px', 
                    backgroundColor: 'rgba(20, 20, 20, 0.7)', 
                    border: '1px solid #444', 
                    borderRadius: '12px', 
                    padding: '25px',
                    textAlign: 'center',
                    transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                    cursor: 'not-allowed',
                    opacity: 0.7
                }}>
                    <div style={{ fontSize: '3rem', marginBottom: '15px' }}>👥</div>
                    <h3 style={{ color: '#E0E0E0', marginBottom: '10px' }}>Управление игроками</h3>
                    <p style={{ color: '#888', fontSize: '0.9rem' }}>Бан, разжалование, назначение мастеров, управление твинами.</p>
                    <div style={{ marginTop: '15px', display: 'inline-block', padding: '5px 15px', backgroundColor: '#333', borderRadius: '20px', fontSize: '0.8rem', color: '#aaa' }}>
                        В разработке
                    </div>
                </div>

                <div 
                    onClick={() => setActiveSection('rewards')}
                    style={{ 
                    flex: '1 1 300px', 
                    backgroundColor: 'rgba(20, 20, 20, 0.7)', 
                    border: '1px solid #444', 
                    borderRadius: '12px', 
                    padding: '25px',
                    textAlign: 'center',
                    transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                    cursor: 'pointer'
                }}
                onMouseOver={(e) => {
                    e.currentTarget.style.borderColor = '#8B0000';
                    e.currentTarget.style.boxShadow = '0 0 15px rgba(209, 0, 31, 0.2)';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseOut={(e) => {
                    e.currentTarget.style.borderColor = '#444';
                    e.currentTarget.style.boxShadow = 'none';
                    e.currentTarget.style.transform = 'translateY(0)';
                }}
                >
                    <div style={{ fontSize: '3rem', marginBottom: '15px' }}>🎁</div>
                    <h3 style={{ color: '#E0E0E0', marginBottom: '10px' }}>Раздача наград</h3>
                    <p style={{ color: '#888', fontSize: '0.9rem' }}>Выдача наград по очередям и отправка уведомлений.</p>
                </div>

                <div style={{ 
                    flex: '1 1 300px', 
                    backgroundColor: 'rgba(20, 20, 20, 0.7)', 
                    border: '1px solid #444', 
                    borderRadius: '12px', 
                    padding: '25px',
                    textAlign: 'center',
                    transition: 'transform 0.2s ease, box-shadow 0.2s ease',
                    cursor: 'not-allowed',
                    opacity: 0.7
                }}>
                    <div style={{ fontSize: '3rem', marginBottom: '15px' }}>📢</div>
                    <h3 style={{ color: '#E0E0E0', marginBottom: '10px' }}>Объявления</h3>
                    <p style={{ color: '#888', fontSize: '0.9rem' }}>Настройка рассылок и системных уведомлений.</p>
                    <div style={{ marginTop: '15px', display: 'inline-block', padding: '5px 15px', backgroundColor: '#333', borderRadius: '20px', fontSize: '0.8rem', color: '#aaa' }}>
                        В разработке
                    </div>
                </div>
            </div>
        </div>
    );
}
