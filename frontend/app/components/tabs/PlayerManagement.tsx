import React, { useEffect, useState, useMemo } from 'react';
import { 
    fetchMasterUsers, 
    toggleUserBan, 
    toggleUserMaster, 
    fetchVerificationCode, 
    updateVerificationCode, 
    fetchMasterAfk,
    fetchMasterAfkHistory,
    saveMasterAfk,
    deleteMasterAfk,
    MasterUser,
    deleteUser
} from '@/lib/api';
import PlayerModal from '../modals/PlayerModal';

interface PlayerManagementProps {
    onBack?: () => void;
}

const PlayerManagement: React.FC<PlayerManagementProps> = ({ onBack }) => {
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'participants' | 'afk' | 'settings'>('participants');
    const [activeSubTab, setActiveSubTab] = useState<'list' | 'history'>('list');
    const [users, setUsers] = useState<MasterUser[]>([]);
    const [stats, setStats] = useState({ 
        total: 0, 
        active: 0, 
        totalChars: 0, 
        charsInClan: 0, 
        totalClanPlayers: 0 
    });
    const [afkPlayers, setAfkPlayers] = useState<any[]>([]);
    const [afkHistory, setAfkHistory] = useState<any[]>([]);
    const [verificationCode, setVerificationCode] = useState('');
    const [searchQuery, setSearchQuery] = useState('');
    const [filter, setFilter] = useState<'all' | 'clan' | 'no_clan' | 'phantom'>('all');
    const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);

    // AFK CRUD state
    const [isSavingAfk, setIsSavingAfk] = useState(false);
    const [afkSearchQuery, setAfkSearchQuery] = useState('');
    const [showAfkForm, setShowAfkForm] = useState(false);
    const [selectedAfkUser, setSelectedAfkUser] = useState<MasterUser | null>(null);
    const [afkDates, setAfkDates] = useState({ start: '', end: '', reason: '' });
    const [isCodeSaved, setIsCodeSaved] = useState(false);

    const loadData = async () => {
        setLoading(true);
        try {
            if (activeTab === 'participants') {
                const data = await fetchMasterUsers();
                setUsers(data.users);
                setStats({ 
                    total: data.total_users, 
                    active: data.active_clan_users,
                    totalChars: data.total_chars,
                    charsInClan: data.chars_in_clan,
                    totalClanPlayers: data.total_clan_players
                });
            } else if (activeTab === 'afk') {
                if (activeSubTab === 'list') {
                    const data = await fetchMasterAfk();
                    setAfkPlayers(data);
                } else if (activeSubTab === 'history') {
                    const data = await fetchMasterAfkHistory();
                    setAfkHistory(data);
                }
            } else if (activeTab === 'settings') {
                const code = await fetchVerificationCode();
                setVerificationCode(code);
            }
        } catch (error) {
            console.error("Failed to fetch data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, [activeTab, activeSubTab]);

    const handleToggleBan = async (userId: number) => {
        try {
            const isBanned = await toggleUserBan(userId);
            setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_banned: isBanned } : u));
        } catch (error: any) {
            alert("Ошибка: " + error.message);
        }
    };

    const handleToggleMaster = async (userId: number) => {
        try {
            const isMaster = await toggleUserMaster(userId);
            setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_master: isMaster } : u));
        } catch (error: any) {
            alert("Ошибка: " + error.message);
        }
    };

    const handleUpdateCode = async () => {
        try {
            await updateVerificationCode(verificationCode);
            setIsCodeSaved(true);
            setTimeout(() => setIsCodeSaved(false), 2000);
        } catch (error: any) {
            alert("Ошибка: " + error.message);
        }
    };

    const handleSaveAfk = async () => {
        console.log("Saving AFK. State:", { selectedAfkUser, afkDates });
        if (!selectedAfkUser) {
            alert("Выберите игрока");
            return;
        }
        if (!afkDates.start || !afkDates.end) {
            alert("Заполните даты отсутствия");
            return;
        }
        setIsSavingAfk(true);
        try {
            await saveMasterAfk(selectedAfkUser.id, afkDates.start, afkDates.end, afkDates.reason);
            setShowAfkForm(false);
            setSelectedAfkUser(null);
            setAfkDates({ start: '', end: '', reason: '' });
            await loadData();
        } catch (error: any) {
            alert("Ошибка сохранения АФК: " + error.message);
        } finally {
            setIsSavingAfk(false);
        }
    };

    const handleDeleteAfk = async (userId: number, nickname: string) => {
        if (!confirm(`Вы уверены, что хотите убрать АФК статус у игрока ${nickname}?`)) return;
        try {
            await deleteMasterAfk(userId);
            await loadData();
        } catch (error: any) {
            alert("Ошибка удаления АФК: " + error.message);
        }
    };

    const handleEditAfk = (p: any) => {
        const user = users.find(u => u.id === p.id);
        if (user) {
            setSelectedAfkUser(user);
            setAfkDates({ start: p.start, end: p.end, reason: p.reason || '' });
            setShowAfkForm(true);
        }
    };

    const handleDeleteUser = async (userId: number, username: string | null) => {
        if (!confirm(`Вы уверены, что хотите НАВСЕГДА удалить пользователя ${username || 'без имени'}? Все его персонажи и данные в очередях будут стерты.`)) {
            return;
        }
        try {
            await deleteUser(userId);
            setUsers(prev => prev.filter(u => u.id !== userId));
        } catch (error: any) {
            alert("Ошибка удаления: " + error.message);
        }
    };

    const filteredUsers = useMemo(() => {
        return users.filter(u => {
            const matchesSearch = (u.username?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
                (u.main_nickname?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
                (u.telegram_id?.toString() || '').includes(searchQuery);
            
            if (filter === 'clan') return matchesSearch && u.is_in_clan && !u.is_phantom;
            if (filter === 'no_clan') return matchesSearch && !u.is_in_clan && !u.is_phantom;
            if (filter === 'phantom') return matchesSearch && u.is_phantom;
            return matchesSearch;
        });
    }, [users, searchQuery, filter]);

    const afkSuggestions = useMemo(() => {
        if (afkSearchQuery.trim().length < 2) return [];
        return users.filter(u => 
            (u.username?.toLowerCase() || '').includes(afkSearchQuery.toLowerCase()) ||
            (u.main_nickname?.toLowerCase() || '').includes(afkSearchQuery.toLowerCase())
        ).slice(0, 5);
    }, [users, afkSearchQuery]);

    const counts = useMemo(() => {
        return {
            no_clan: users.filter(u => !u.is_in_clan && !u.is_phantom).length,
            phantom: users.filter(u => u.is_phantom).length
        };
    }, [users]);

    const clanRegistrationPercent = useMemo(() => {
        if (stats.totalClanPlayers === 0) return 0;
        return Math.round((stats.charsInClan / stats.totalClanPlayers) * 100);
    }, [stats.charsInClan, stats.totalClanPlayers]);

    return (
        <div className="pm-layout" style={{ 
            display: 'flex', 
            minHeight: '800px', 
            background: 'linear-gradient(135deg, #0a0a0b 0%, #111114 100%)',
            color: '#ddd',
            fontFamily: "'Inter', sans-serif"
        }}>
            {/* Sidebar */}
            <div className="pm-sidebar" style={{ 
                width: '280px', 
                background: '#0d0d0f', 
                borderRight: '1px solid #1e1e22',
                padding: '24px 0',
                display: 'flex',
                flexDirection: 'column',
                boxShadow: '4px 0 15px rgba(0,0,0,0.3)',
                zIndex: 10
            }}>
                {onBack && (
                    <div style={{ padding: '0 20px 20px', borderBottom: '1px solid #1e1e22' }}>
                        <button 
                            onClick={onBack}
                            style={{
                                width: '100%',
                                background: '#1a1a1a',
                                border: '1px solid #333',
                                color: '#ccc',
                                padding: '10px 12px',
                                borderRadius: '6px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px',
                                cursor: 'pointer',
                                fontSize: '0.85rem',
                                transition: 'all 0.2s',
                                fontFamily: "'Cinzel', serif"
                            }}
                            onMouseOver={(e) => {
                                e.currentTarget.style.borderColor = '#ff4d6d';
                                e.currentTarget.style.color = '#fff';
                            }}
                            onMouseOut={(e) => {
                                e.currentTarget.style.borderColor = '#333';
                                e.currentTarget.style.color = '#ccc';
                            }}
                        >
                            <span style={{ fontSize: '1.2rem' }}>←</span> В МЕНЮ
                        </button>
                    </div>
                )}
                <div className="no-scrollbar" style={{ padding: '20px 0', flex: 1, overflowY: 'auto' }}>
                    {/* Участники section header */}
                    <h3 style={{
                        color: '#ccc',
                        fontSize: '0.85rem',
                        fontFamily: "'Cinzel', serif",
                        letterSpacing: '1px',
                        marginLeft: '20px',
                        marginBottom: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        textTransform: 'uppercase'
                    }}>
                        <div style={{ width: '3px', height: '16px', backgroundColor: activeTab === 'participants' ? '#ff4d6d' : '#444', borderRadius: '2px' }}></div>
                        Участники
                    </h3>

                    {/* Sub-filter items */}
                    <div style={{ padding: '0 8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        {[
                            { id: 'all', label: 'Все', icon: 'ri-group-line', count: stats.total },
                            { id: 'clan', label: 'В гильдии', icon: 'ri-shield-user-line', count: stats.active },
                            { id: 'no_clan', label: 'Не в гильдии', icon: 'ri-user-unfollow-line', count: counts.no_clan },
                            { id: 'phantom', label: 'Фантомы', icon: 'ri-ghost-line', count: counts.phantom },
                        ].map((item) => {
                            const isActive = activeTab === 'participants' && filter === item.id;
                            return (
                                <button 
                                    key={item.id}
                                    className={`pm-nav-sub-item ${isActive ? 'active' : ''}`}
                                    onClick={() => { setActiveTab('participants'); setFilter(item.id as any); }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <i className={item.icon} style={{ fontSize: '0.9rem', opacity: 0.7 }}></i>
                                        <span>{item.label}</span>
                                    </div>
                                    {item.count !== null && (
                                        <span className="pm-nav-count">{item.count}</span>
                                    )}
                                </button>
                            );
                        })}
                    </div>

                    {/* AFK section */}
                    <button 
                        className={`pm-nav-section-header ${activeTab === 'afk' ? 'active' : ''}`}
                        onClick={() => { setActiveTab('afk'); setActiveSubTab('list'); }}
                    >
                        <i className="ri-zzz-line"></i>
                        AFK
                    </button>
                    <div style={{ padding: '0 8px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <button 
                            className={`pm-nav-sub-item ${activeTab === 'afk' && activeSubTab === 'list' ? 'active' : ''}`}
                            onClick={() => { setActiveTab('afk'); setActiveSubTab('list'); }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <i className="ri-list-check" style={{ fontSize: '0.9rem', opacity: 0.7 }}></i>
                                <span>Список АФК</span>
                            </div>
                        </button>
                        <button 
                            className={`pm-nav-sub-item ${activeTab === 'afk' && activeSubTab === 'history' ? 'active' : ''}`}
                            onClick={() => { setActiveTab('afk'); setActiveSubTab('history'); }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <i className="ri-history-line" style={{ fontSize: '0.9rem', opacity: 0.7 }}></i>
                                <span>История</span>
                            </div>
                        </button>
                    </div>

                    {/* Settings section */}
                    <button 
                        className={`pm-nav-section-header ${activeTab === 'settings' ? 'active' : ''}`}
                        onClick={() => setActiveTab('settings')}
                    >
                        <i className="ri-settings-3-line"></i>
                        Настройки
                    </button>
                    <div style={{ padding: '0 8px' }}>
                        <button
                            className={`pm-nav-sub-item ${activeTab === 'settings' ? 'active' : ''}`}
                            onClick={() => setActiveTab('settings')}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <i className="ri-user-settings-line" style={{ fontSize: '0.9rem', opacity: 0.7 }}></i>
                                <span>Регистрация</span>
                            </div>
                        </button>
                    </div>

                    {/* Stats at the bottom of sidebar */}
                    <div style={{
                        marginTop: '24px',
                        borderTop: '1px solid #1e1e1e',
                        padding: '16px 20px 8px',
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <span style={{ fontSize: '0.7rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Персонажей</span>
                            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#4da6ff' }}>{stats.totalChars}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                            <span style={{ fontSize: '0.7rem', color: '#aaa', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Охват</span>
                            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: '#39e600' }}>{clanRegistrationPercent}%</span>
                        </div>
                        <div style={{ height: '3px', background: '#1a1a1a', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${clanRegistrationPercent}%`, background: '#39e600', borderRadius: '2px' }}></div>
                        </div>
                        <div style={{ fontSize: '0.65rem', color: '#888', textAlign: 'right', marginTop: '4px' }}>
                            <span style={{ color: '#fff' }}>{stats.charsInClan}</span> из <span style={{ color: '#fff' }}>{stats.totalClanPlayers}</span> в ГИ
                        </div>
                    </div>
                </div>
            </div>

            {/* Main Content Area */}
            <div className="pm-main" style={{ 
                flex: 1, 
                padding: activeTab === 'participants' ? '30px 40px' : '30px 60px', 
                overflowY: 'auto',
                position: 'relative'
            }}>
                <div className="pm-content-container" style={{ maxWidth: '1100px', margin: '0 auto' }}>
                    {loading ? (
                        <div className="loading-state" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px', opacity: 0.5 }}>
                            <div className="spinner"></div>
                            <span style={{ marginLeft: '15px', fontFamily: "'Cinzel', serif", letterSpacing: '2px' }}>ЗАГРУЗКА...</span>
                        </div>
                    ) : (
                        <>
                            {activeTab === 'participants' && (
                                <div className="players-tab-view animate-fade-in">
                                    {/* Tab Header & Search */}
                                    <div className="tab-controls" style={{ 
                                        display: 'flex', 
                                        justifyContent: 'space-between', 
                                        alignItems: 'center', 
                                        marginBottom: '15px',
                                        gap: '20px'
                                    }}>
                                        <div className="search-wrapper" style={{ position: 'relative', flex: 1, maxWidth: '500px' }}>
                                            <i className="ri-search-line" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#666' }}></i>
                                            <input 
                                                type="text" 
                                                className="gothic-input"
                                                placeholder="Поиск по нику, Telegram ID..."
                                                value={searchQuery}
                                                onChange={(e) => setSearchQuery(e.target.value)}
                                                style={{ 
                                                    width: '100%', 
                                                    padding: '10px 15px 10px 40px', 
                                                    background: '#151517', 
                                                    border: '1px solid #222', 
                                                    borderRadius: '8px',
                                                    color: '#fff'
                                                }}
                                            />
                                        </div>
                                    </div>

                                    <div className="table-wrapper glass-panel shadow-premium" style={{ border: '1px solid #1e1e22' }}>
                                        <table className="gothic-table">
                                            <thead>
                                                <tr>
                                                    <th>Пользователь</th>
                                                    <th>Персонаж</th>
                                                    <th>Гильдия</th>
                                                    <th>Твины</th>
                                                    <th>Статус</th>
                                                    <th style={{ textAlign: 'right' }}>Управление</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {filteredUsers.map(u => (
                                                    <tr key={u.id} className={u.is_banned ? 'row-banned' : ''}>
                                                        <td>
                                                            <div className="user-info">
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                    <span className="username" style={{ color: '#aaa', fontWeight: 600 }}>@{u.username || 'unknown'}</span>
                                                                    {!u.is_phantom && (u.username || u.telegram_id) && (
                                                                        <a
                                                                            href={u.username
                                                                                ? `https://t.me/${u.username}`
                                                                                : `https://web.telegram.org/k/#${u.telegram_id}`
                                                                            }
                                                                            target="_blank"
                                                                            rel="noopener noreferrer"
                                                                            style={{ color: '#4a6fa5', fontSize: '1rem', opacity: 0.8 }}
                                                                        >
                                                                            <i className="ri-telegram-fill"></i>
                                                                        </a>
                                                                    )}
                                                                </div>
                                                                <span className="tg-id" style={{ fontSize: '0.65rem', color: '#444' }}>ID: {u.telegram_id}</span>
                                                            </div>
                                                        </td>
                                                        <td>
                                                            <span className={u.main_nickname ? "nickname" : "nickname text-muted"} style={{ fontWeight: 500, color: u.main_nickname ? '#88B0D3' : undefined }}>
                                                                {u.main_nickname || 'Не привязан'}
                                                            </span>
                                                        </td>
                                                        <td>
                                                            {u.is_in_clan ? (
                                                                <div className="clan-badge in-clan">
                                                                    <div className="dot"></div> В Гильдии
                                                                </div>
                                                            ) : (
                                                                <div className="clan-badge out-clan">
                                                                    <div className="dot"></div> Вне Клана
                                                                </div>
                                                            )}
                                                        </td>
                                                        <td>
                                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                                                                {u.characters.filter(c => !c.is_main).length > 0 ? u.characters.filter(c => !c.is_main).map(alt => (
                                                                    <span key={alt.nickname} style={{ background: '#111', color: '#777', padding: '2px 8px', borderRadius: '4px', fontSize: '0.7rem', border: '1px solid #222' }}>{alt.nickname}</span>
                                                                )) : <span style={{ color: '#444' }}>—</span>}
                                                            </div>
                                                        </td>
                                                        <td>
                                                            <div style={{ display: 'flex', gap: '6px' }}>
                                                                {u.is_master && <span style={{ background: '#5e0000', color: '#ccc', padding: '2px 8px', borderRadius: '4px', fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.5px', border: '1px solid #8b000044' }}>MASTER</span>}
                                                                {u.is_phantom && <span style={{ background: '#2d004d', color: '#ccc', padding: '2px 8px', borderRadius: '4px', fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.5px', border: '1px solid #4b008244' }}>PHANTOM</span>}
                                                                {u.is_banned && <span style={{ background: '#222', color: '#666', padding: '2px 8px', borderRadius: '4px', fontSize: '0.6rem', fontWeight: 700, letterSpacing: '0.5px', border: '1px solid #333' }}>BANNED</span>}
                                                            </div>
                                                        </td>
                                                        <td style={{ textAlign: 'right' }}>
                                                            <div className="actions-group" style={{ justifyContent: 'flex-end' }}>
                                                                <button className="action-btn edit" onClick={() => setSelectedRoleId(u.main_role_id || null)} disabled={!u.main_role_id}>📝</button>
                                                                <button className={`action-btn master ${u.is_master ? 'active' : ''}`} onClick={() => handleToggleMaster(u.id)}>👑</button>
                                                                <button className={`action-btn ban ${u.is_banned ? 'active' : ''}`} onClick={() => handleToggleBan(u.id)}>{u.is_banned ? '🕊️' : '🔨'}</button>
                                                                <button className="action-btn delete" onClick={() => handleDeleteUser(u.id, u.username)}>🗑️</button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'afk' && activeSubTab === 'list' && (
                                <div className="afk-container animate-fade-in" style={{ padding: '0 10px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px' }}>
                                        <h2 style={{ color: '#eee', fontFamily: "'Cinzel', serif", margin: 0, fontSize: '1.4rem', letterSpacing: '1px' }}>🏖️ Список АФК</h2>
                                        <button 
                                            className="gothic-btn" 
                                            onClick={() => setShowAfkForm(!showAfkForm)}
                                            style={{ padding: '8px 20px', fontSize: '0.8rem' }}
                                        >
                                            {showAfkForm ? 'ЗАКРЫТЬ' : 'ДОБАВИТЬ ЗАПИСЬ'}
                                        </button>
                                    </div>

                                    {showAfkForm && (
                                        <div style={{ background: '#151517', border: '1px solid #ff4d6d44', padding: '25px', borderRadius: '12px', marginBottom: '30px', animation: 'fadeIn 0.3s ease', boxShadow: '0 4px 20px rgba(0,0,0,0.4)', position: 'relative', zIndex: 10, minWidth: '950px' }}>
                                            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(200px, 1.5fr) minmax(130px, 1fr) minmax(130px, 1fr) minmax(200px, 2fr) auto', gap: '30px', alignItems: 'end' }}>
                                                <div style={{ position: 'relative' }}>
                                                    <label style={{ display: 'block', color: '#ff4d6d', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>Игрок</label>
                                                    {selectedAfkUser ? (
                                                        <div style={{ background: '#0a0a0a', border: '1px solid #333', padding: '10px 14px', borderRadius: '8px', color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: '42px', boxSizing: 'border-box' }}>
                                                            <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selectedAfkUser.main_nickname || selectedAfkUser.username}</span>
                                                            <i className="ri-close-line" style={{ cursor: 'pointer', color: '#ff4d6d', fontSize: '1.2rem', marginLeft: '8px' }} onClick={() => setSelectedAfkUser(null)}></i>
                                                        </div>
                                                    ) : (
                                                        <>
                                                            <input 
                                                                type="text"
                                                                placeholder="Поиск игрока..."
                                                                value={afkSearchQuery}
                                                                onChange={e => setAfkSearchQuery(e.target.value)}
                                                                style={{ width: '100%', background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px 14px', borderRadius: '8px', fontSize: '0.9rem', height: '42px', boxSizing: 'border-box' }}
                                                            />
                                                            {afkSuggestions.length > 0 && (
                                                                <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#1a1a1a', border: '1px solid #444', borderRadius: '8px', zIndex: 100, marginTop: '8px', boxShadow: '0 8px 25px rgba(0,0,0,0.6)', overflow: 'hidden' }}>
                                                                    {afkSuggestions.map(u => (
                                                                        <div 
                                                                            key={u.id}
                                                                            onClick={() => { setSelectedAfkUser(u); setAfkSearchQuery(''); }}
                                                                            style={{ padding: '12px 14px', cursor: 'pointer', borderBottom: '1px solid #222', fontSize: '0.9rem' }}
                                                                            onMouseOver={e => e.currentTarget.style.backgroundColor = '#2a2a2e'}
                                                                            onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                                                        >
                                                                            <span style={{ color: '#88B0D3', fontWeight: 500 }}>{u.main_nickname}</span>
                                                                            <span style={{ color: '#666', fontSize: '0.75rem', marginLeft: '8px' }}>@{u.username}</span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </>
                                                    )}
                                                </div>
                                                <div style={{ position: 'relative' }}>
                                                    <label style={{ display: 'block', color: '#888', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '8px', whiteSpace: 'nowrap' }}>С даты</label>
                                                    <input 
                                                        type="date" 
                                                        value={afkDates.start}
                                                        onChange={e => setAfkDates({...afkDates, start: e.target.value})}
                                                        style={{ width: '100%', background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px', borderRadius: '8px', fontSize: '0.9rem', height: '42px', boxSizing: 'border-box' }}
                                                    />
                                                </div>
                                                <div style={{ position: 'relative' }}>
                                                    <label style={{ display: 'block', color: '#888', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '8px', whiteSpace: 'nowrap' }}>По дату</label>
                                                    <input 
                                                        type="date" 
                                                        value={afkDates.end}
                                                        onChange={e => setAfkDates({...afkDates, end: e.target.value})}
                                                        style={{ width: '100%', background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px', borderRadius: '8px', fontSize: '0.9rem', height: '42px', boxSizing: 'border-box' }}
                                                    />
                                                </div>
                                                <div style={{ position: 'relative' }}>
                                                    <label style={{ display: 'block', color: '#888', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '8px', whiteSpace: 'nowrap' }}>Причина</label>
                                                    <input 
                                                        type="text" 
                                                        placeholder="Причина (опционально)..."
                                                        value={afkDates.reason}
                                                        onChange={e => setAfkDates({...afkDates, reason: e.target.value})}
                                                        style={{ width: '100%', background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px 14px', borderRadius: '8px', fontSize: '0.9rem', height: '42px', boxSizing: 'border-box' }}
                                                    />
                                                </div>
                                                <button 
                                                    className="gothic-btn" 
                                                    onClick={handleSaveAfk}
                                                    disabled={isSavingAfk}
                                                    style={{ padding: '0 25px', height: '42px', minWidth: '80px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                                                >
                                                    {isSavingAfk ? '...' : 'OK'}
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    <div className="table-wrapper glass-panel shadow-premium" style={{ border: '1px solid #1e1e22' }}>
                                        <table className="gothic-table compact">
                                            <thead>
                                                <tr>
                                                    <th style={{ textAlign: 'left', width: '25%' }}>Игрок</th>
                                                    <th style={{ textAlign: 'left', width: '30%' }}>Период Отсутствия</th>
                                                    <th style={{ textAlign: 'left', width: '30%' }}>Причина</th>
                                                    <th style={{ textAlign: 'right', width: '15%' }}>Управление</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {afkPlayers.length > 0 ? afkPlayers.map((p, idx) => (
                                                    <tr key={idx}>
                                                        <td style={{ textAlign: 'left' }}><span style={{ color: '#88B0D3', fontWeight: 500 }}>{p.nickname}</span></td>
                                                        <td style={{ textAlign: 'left' }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                                <span style={{ color: '#ccc', fontSize: '0.85rem' }}>{p.start}</span>
                                                                <span style={{ color: '#444' }}>→</span>
                                                                <span style={{ color: '#ccc', fontSize: '0.85rem' }}>{p.end}</span>
                                                            </div>
                                                        </td>
                                                        <td style={{ textAlign: 'left' }}><span style={{ color: '#888', fontSize: '0.85rem' }}>{p.reason || '—'}</span></td>
                                                        <td style={{ textAlign: 'right' }}>
                                                            <div className="actions-group" style={{ justifyContent: 'flex-end' }}>
                                                                <button className="action-btn edit" title="Редактировать" onClick={() => handleEditAfk(p)}>📝</button>
                                                                <button className="action-btn delete" title="Удалить" onClick={() => handleDeleteAfk(p.id, p.nickname)}>🗑️</button>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                )) : (
                                                    <tr>
                                                        <td colSpan={4} className="text-center p-5 text-muted" style={{ fontFamily: "'Cinzel', serif", letterSpacing: '1px' }}>Список AFK пуст</td>
                                                    </tr>
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'afk' && activeSubTab === 'history' && (
                                <div className="afk-history-container animate-fade-in" style={{ padding: '0 10px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
                                        <h2 style={{ color: '#eee', fontFamily: "'Cinzel', serif", margin: 0, fontSize: '1.4rem', letterSpacing: '1px' }}>📜 История АФК</h2>
                                    </div>

                                    <div className="history-timeline" style={{ position: 'relative', paddingLeft: '30px', borderLeft: '2px solid #1e1e22', marginLeft: '10px' }}>
                                        {afkHistory.length > 0 ? afkHistory.map((h, idx) => (
                                            <div key={idx} className="timeline-item" style={{ marginBottom: '35px', position: 'relative' }}>
                                                <div className="timeline-dot" style={{ 
                                                    position: 'absolute', 
                                                    left: '-41px', 
                                                    top: '5px', 
                                                    width: '20px', 
                                                    height: '20px', 
                                                    borderRadius: '50%', 
                                                    background: '#111', 
                                                    border: '2px solid #ff4d6d',
                                                    boxShadow: '0 0 10px rgba(255, 77, 109, 0.3)'
                                                }}></div>
                                                
                                                <div className="timeline-card" style={{ 
                                                    background: '#151517', 
                                                    border: '1px solid #1e1e22', 
                                                    borderRadius: '12px', 
                                                    padding: '20px',
                                                    boxShadow: '0 4px 15px rgba(0,0,0,0.2)'
                                                }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px', alignItems: 'center' }}>
                                                        <span style={{ fontSize: '1.05rem', color: '#88B0D3', fontWeight: 500, fontFamily: "'Cinzel', serif" }}>{h.nickname}</span>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: '#888', background: '#0a0a0a', padding: '6px 12px', borderRadius: '20px', border: '1px solid #222' }}>
                                                            <i className="ri-calendar-event-line" style={{ color: '#ff4d6d' }}></i>
                                                            <span>{h.start}</span>
                                                            <span style={{ opacity: 0.3 }}>→</span>
                                                            <span>{h.end}</span>
                                                        </div>
                                                    </div>
                                                    <div style={{ color: '#aaa', fontSize: '0.95rem', fontStyle: h.reason ? 'normal' : 'italic', borderTop: '1px solid #222', paddingTop: '12px' }}>
                                                        <span style={{ color: '#555', marginRight: '8px', fontSize: '0.8rem', textTransform: 'uppercase' }}>Причина:</span>
                                                        {h.reason || 'Причина не указана'}
                                                    </div>
                                                </div>
                                            </div>
                                        )) : (
                                            <div style={{ textAlign: 'center', padding: '50px', color: '#666', fontFamily: "'Cinzel', serif" }}>История АФК пуста</div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {activeTab === 'settings' && (
                                <div className="settings-view animate-fade-in" style={{ padding: '0 20px' }}>
                                    <div style={{ maxWidth: '800px', margin: '0 auto' }}>
                                        <h2 style={{ color: '#eee', fontFamily: "'Cinzel', serif", marginBottom: '30px', display: 'flex', alignItems: 'center', gap: '15px', fontSize: '1.4rem', letterSpacing: '1px' }}>
                                            <i className="ri-settings-3-line" style={{ color: '#ff4d6d' }}></i> Настройки Регистрации
                                        </h2>
                                        <div style={{ background: '#151517', border: '1px solid #1e1e22', padding: '35px', borderRadius: '15px', display: 'flex', alignItems: 'center', gap: '30px', boxShadow: '0 8px 30px rgba(0,0,0,0.4)', transition: 'all 0.3s ease' }}>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ color: '#fff', fontWeight: 600, marginBottom: '10px', fontSize: '1.1rem', fontFamily: "'Cinzel', serif" }}>Глобальный код верификации</div>
                                                <div style={{ color: '#777', fontSize: '0.9rem', lineHeight: '1.5' }}>
                                                    Этот код необходим новым участникам для привязки персонажа через бота. Без кода регистрация невозможна.
                                                    <br /><br />
                                                    Код можно не устанавливать, тогда бот не будет спрашивать код у пользователей при привязке персонажа.
                                                    Чтобы сбросить код, оставьте поле пустым и нажмите "Ок".
                                                    <br /><br />
                                                    <strong>Рекомендация:</strong> пропишите код в описании клан листа. В таком случае код смогут посмотреть в любое время участники гильдии, и сторонние пользователи не смогут пользоваться ботом, привязав никнейм не своего персонажа.
                                                </div>
                                            </div>
                                            <div style={{ display: 'flex', gap: '15px' }}>
                                                <input
                                                    type="text"
                                                    value={verificationCode}
                                                    onChange={(e) => setVerificationCode(e.target.value)}
                                                    placeholder="..."
                                                    className={isCodeSaved ? 'success-pulse' : ''}
                                                    style={{ 
                                                        width: '150px', 
                                                        background: '#0a0a0a', 
                                                        border: isCodeSaved ? '1px solid #39e600' : '1px solid #333', 
                                                        color: isCodeSaved ? '#39e600' : '#ffc107', 
                                                        padding: '14px', 
                                                        borderRadius: '10px', 
                                                        fontSize: '1.1rem', 
                                                        textAlign: 'center', 
                                                        outline: 'none', 
                                                        fontWeight: 'bold', 
                                                        letterSpacing: '2px',
                                                        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                                                        boxShadow: isCodeSaved ? '0 0 15px rgba(57, 230, 0, 0.3)' : 'none'
                                                    }}
                                                />
                                                <button className="gothic-btn" onClick={handleUpdateCode} style={{ padding: '12px 25px' }}>ПРИМЕНИТЬ</button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>


            {selectedRoleId && (
                <PlayerModal
                    roleId={selectedRoleId}
                    onClose={() => setSelectedRoleId(null)}
                    onSave={() => loadData()}
                />
            )}

            <style jsx>{`
                /* ============ SIDEBAR LAYOUT ============ */
                .pm-layout {
                    display: grid;
                    grid-template-columns: 220px 1fr;
                    gap: 20px;
                    align-items: start;
                    font-family: 'Inter', sans-serif;
                    color: #ddd;
                    padding: 10px 0;
                }

                /* Sidebar */
                .pm-sidebar {
                    background: rgba(15, 15, 18, 0.8);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 12px;
                    padding: 12px 8px;
                    position: sticky;
                    top: 80px;
                }

                /* Section headers (Участники / AFK / Настройки) */
                .pm-nav-section {
                    margin-bottom: 4px;
                }
                .pm-nav-section-header {
                    width: 100%;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    padding: 10px 12px;
                    background: transparent;
                    border: none;
                    border-radius: 8px;
                    color: #777;
                    font-size: 0.85rem;
                    font-weight: 600;
                    font-family: 'Cinzel', serif;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                    cursor: pointer;
                    transition: all 0.2s;
                    text-align: left;
                }
                .pm-nav-section-header i {
                    font-size: 1rem;
                    flex-shrink: 0;
                }
                .pm-nav-section-header:hover {
                    background: rgba(255,255,255,0.04);
                    color: #bbb;
                }
                .pm-nav-section-header.active {
                    color: #e0e0e0;
                    background: rgba(139, 0, 0, 0.15);
                    border-left: 2px solid #8b0000;
                }

                /* Sub-items (Все / В гильдии / ...) */
                .pm-nav-sub {
                    margin-top: 4px;
                    margin-bottom: 8px;
                    display: flex;
                    flex-direction: column;
                    gap: 2px;
                }
                .pm-nav-sub-item {
                    width: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    padding: 7px 12px 7px 30px;
                    background: transparent;
                    border: none;
                    border-radius: 6px;
                    color: #666;
                    font-size: 0.8rem;
                    font-family: 'Montserrat', sans-serif;
                    cursor: pointer;
                    transition: all 0.15s;
                    text-align: left;
                }
                .pm-nav-sub-item:hover {
                    background: rgba(255,255,255,0.04);
                    color: #aaa;
                }
                .pm-nav-sub-item.active {
                    background: rgba(139, 0, 0, 0.12);
                    color: #fff;
                }
                .pm-nav-count {
                    font-size: 0.7rem;
                    background: rgba(255,255,255,0.07);
                    border-radius: 10px;
                    padding: 1px 7px;
                    color: #888;
                }
                .pm-nav-sub-item.active .pm-nav-count {
                    background: rgba(139,0,0,0.3);
                    color: #ddd;
                }

                /* Sidebar stats block */
                .pm-sidebar-stats {
                    margin-top: 16px;
                    border-top: 1px solid rgba(255,255,255,0.06);
                    padding: 14px 12px 6px;
                }
                .pm-stat-row {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 6px;
                }
                .pm-stat-label {
                    font-size: 0.7rem;
                    color: #666;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }
                .pm-stat-val {
                    font-size: 0.9rem;
                    font-weight: 700;
                }
                .pm-mini-bar {
                    height: 3px;
                    background: rgba(255,255,255,0.08);
                    border-radius: 2px;
                    overflow: hidden;
                    margin: 4px 0;
                }
                .pm-mini-bar-fill {
                    height: 100%;
                    background: #2ecc71;
                    border-radius: 2px;
                    box-shadow: 0 0 6px rgba(46,204,113,0.4);
                }
                .pm-stat-sub {
                    font-size: 0.65rem;
                    color: #555;
                    text-align: right;
                    margin-top: 4px;
                }

                /* Main content area */
                .pm-main {
                    min-width: 0;
                }

                /* Search bar */
                .pm-search-bar {
                    position: relative;
                    margin-bottom: 16px;
                }
                .pm-search-icon {
                    position: absolute;
                    left: 15px;
                    top: 50%;
                    transform: translateY(-50%);
                    color: #555;
                    font-size: 1rem;
                }
                .pm-search-input {
                    width: 100%;
                    background: rgba(0,0,0,0.4);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 10px;
                    padding: 10px 15px 10px 42px;
                    color: #ddd;
                    font-size: 0.9rem;
                    outline: none;
                    transition: border-color 0.2s;
                }
                .pm-search-input::placeholder { color: #444; }
                .pm-search-input:focus {
                    border-color: rgba(139,0,0,0.5);
                    box-shadow: 0 0 0 3px rgba(139,0,0,0.1);
                }

                .text-muted-alt { color: #888; font-size: 0.85rem; }

                /* Shared panels */
                .glass-panel {
                    background: rgba(20, 20, 20, 0.4);
                    backdrop-filter: blur(15px);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 12px;
                }
                .shadow-premium {
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
                }

                /* Unused (kept for safety) */
                .premium-tabs-wrapper {
                    background: rgba(0, 0, 0, 0.3);
                    border-radius: 12px;
                    padding: 4px;
                    border: 1px solid rgba(255, 255, 255, 0.05);
                }
                .premium-tabs-container {
                    display: flex;
                    position: relative;
                    gap: 4px;
                }
                .p-tab-btn {
                    padding: 8px 24px;
                    border: none;
                    background: transparent;
                    color: #777;
                    font-size: 0.85rem;
                    font-weight: 600;
                    border-radius: 8px;
                    z-index: 2;
                    transition: all 0.3s;
                    cursor: pointer;
                }
                .p-tab-btn:hover { color: #aaa; }
                .p-tab-btn.active { color: #e0e0e0; }
                
                .p-tab-slider {
                    position: absolute;
                    height: 100%;
                    background: linear-gradient(135deg, #8b0000, #5a0000);
                    border-radius: 8px;
                    z-index: 1;
                    transition: all 0.4s cubic-bezier(0.18, 0.89, 0.32, 1.28);
                    box-shadow: 0 4px 15px rgba(139, 0, 0, 0.3);
                }
                .tab-players { left: 0; width: 125px; } 
                .tab-afk { left: 129px; width: 75px; }
                .tab-settings { left: 208px; width: 120px; }

                /* Controls Row V2 */
                .controls-row-v2 {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    max-width: 1100px;
                    margin: 40px auto 15px;
                    padding-left: 15px;
                }
                .controls-search-box {
                    position: relative;
                    flex: 1;
                }
                .search-icon-v2 {
                    position: absolute;
                    left: 15px; top: 50%;
                    transform: translateY(-50%);
                    color: #555;
                    font-size: 1.1rem;
                }
                .search-input-v2 {
                    width: 100%;
                    background: rgba(0, 0, 0, 0.4);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    padding: 12px 15px 12px 45px;
                    color: #e0e0e0;
                    font-size: 0.95rem;
                    transition: all 0.3s;
                }
                .search-input-v2:focus {
                    border-color: #8b0000;
                    background: rgba(0, 0, 0, 0.6);
                    box-shadow: 0 0 15px rgba(139, 0, 0, 0.2);
                    outline: none;
                }

                .controls-filter-group {
                    display: flex;
                    background: rgba(0, 0, 0, 0.2);
                    border-radius: 10px;
                    padding: 4px;
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    gap: 4px;
                }
                .filter-btn-v2 {
                    flex: 1;
                    padding: 8px 15px;
                    border: none;
                    background: transparent;
                    color: #555;
                    font-size: 0.8rem;
                    font-weight: 700;
                    border-radius: 7px;
                    transition: all 0.3s;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }
                .filter-btn-v2:hover { color: #888; background: rgba(255,255,255,0.02); }
                .filter-btn-v2.active {
                    background: rgba(255, 255, 255, 0.05);
                    color: #eee;
                    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3);
                }

                /* Table */
                .table-wrapper {
                    max-width: 1100px;
                    margin: 0 auto;
                    overflow: hidden;
                }
                .gothic-table { width: 100%; border-collapse: separate; border-spacing: 0; }
                .gothic-table th {
                    padding: 12px 15px;
                    background: rgba(40, 40, 40, 0.2);
                    text-transform: uppercase;
                    font-size: 0.7rem;
                    letter-spacing: 0.1em;
                    color: #888;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    font-weight: 800;
                }
                .gothic-table td { padding: 10px 15px; border-bottom: 1px solid rgba(255, 255, 255, 0.03); font-size: 0.85rem; }
                .gothic-table tr:hover td { background: rgba(255, 255, 255, 0.01); }
                
                .user-info { display: flex; flex-direction: column; }
                .tg-link-icon {
                    color: #00d2ff;
                    font-size: 1.2rem;
                    transition: all 0.3s;
                    display: flex;
                    align-items: center;
                    text-decoration: none;
                    filter: drop-shadow(0 0 5px rgba(0, 210, 255, 0.3));
                }
                .tg-link-icon:hover {
                    transform: scale(1.2);
                    color: #fff;
                    filter: drop-shadow(0 0 10px rgba(0, 210, 255, 0.6));
                }
                .username { color: #aaa; font-weight: 600; font-size: 0.9rem; margin-bottom: 2px; transition: color 0.2s; }
                .username:hover { color: #fff; }
                .tg-id { font-size: 0.65rem; color: #444; font-family: monospace; opacity: 0.6; }

                .nickname { font-weight: 700; font-size: 0.95rem; }
                
                /* Clan Badges */
                .clan-badge {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    padding: 5px 12px;
                    border-radius: 30px;
                    font-size: 0.75rem;
                    font-weight: 700;
                    white-space: nowrap;
                }
                .clan-badge .dot { width: 6px; height: 6px; border-radius: 50%; }
                .in-clan { background: rgba(36, 161, 72, 0.08); color: #24a148; border: 1px solid rgba(36, 161, 72, 0.1); }
                .in-clan .dot { background: #24a148; box-shadow: 0 0 8px rgba(36, 161, 72, 0.4); }
                .out-clan { background: rgba(150, 150, 150, 0.05); color: #666; border: 1px solid rgba(150, 150, 150, 0.1); }
                .out-clan .dot { background: #555; }

                .alts-list { display: flex; flex-wrap: wrap; gap: 5px; }
                .alt-tag { background: rgba(0,0,0,0.3); color: #777; padding: 3px 8px; border-radius: 6px; font-size: 0.7rem; border: 1px solid rgba(255,255,255,0.05); }

                .status-container { display: flex; gap: 6px; }
                .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.6rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }
                .master-badge { background: #5e0000; color: #ccc; border: 1px solid #8b000044; }
                .banned-badge { background: #222; color: #666; border: 1px solid #333; }
                .phantom-badge { background: #2d004d; color: #ccc; border: 1px solid #4b008244; }
                .active-badge { background: rgba(43, 194, 83, 0.1); color: #27ae60; }

                /* Actions */
                .actions-group { display: flex; gap: 8px; justify-content: flex-end; }
                .action-btn {
                    width: 34px;
                    height: 34px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: rgba(30, 30, 30, 0.4);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 8px;
                    font-size: 1rem;
                    transition: all 0.3s;
                    cursor: pointer;
                }
                .action-btn:hover:not(:disabled) {
                    background: rgba(60, 60, 60, 0.6);
                    border-color: rgba(255,255,255,0.2);
                    transform: translateY(-2px);
                }
                .action-btn:disabled { opacity: 0.2; cursor: not-allowed; }
                .action-btn.active.master { color: #d4af37; border-color: #d4af37; background: rgba(212, 175, 55, 0.05); box-shadow: 0 0 10px rgba(212, 175, 55, 0.2); }
                .action-btn.active.ban { color: #ff4d4d; border-color: #ff4d4d; background: rgba(255, 77, 77, 0.05); box-shadow: 0 0 10px rgba(255, 77, 77, 0.2); }
                .action-btn.delete:hover { color: #ff4d4d; border-color: #ff4d4d; background: rgba(255, 77, 77, 0.1); }

                /* Settings Premium Card */
                .settings-card-premium {
                    background: rgba(30, 30, 30, 0.3);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 20px;
                    padding: 60px;
                    max-width: 600px;
                    margin: 0 auto;
                    text-align: center;
                    position: relative;
                    box-shadow: 0 20px 50px rgba(0,0,0,0.5);
                }
                .ornament-premium {
                    position: absolute;
                    top: 10px; left: 10px; right: 10px; bottom: 10px;
                    border: 1px solid rgba(212, 175, 55, 0.05);
                    border-radius: 15px;
                    pointer-events: none;
                }
                
                .animate-fade-in { animation: fadeIn 0.5s ease-out; }
                @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }

                /* Loader */
                .loader-container { padding: 100px; display: flex; justify-content: center; }
                .gothic-loader {
                    width: 48px;
                    height: 48px;
                    border: 3px solid rgba(139, 0, 0, 0.2);
                    border-radius: 50%;
                    border-top-color: #8b0000;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin { to { transform: rotate(360deg); } }

                /* Settings */
                .verification-code-group {
                    text-align: center;
                }
                .code-input-wrapper { 
                    display: flex; 
                    gap: 15px; 
                    margin-bottom: 25px; 
                    align-items: center;
                }
                .code-input {
                    flex: 1;
                    background: rgba(0,0,0,0.5);
                    border: 1px solid rgba(255,255,255,0.1);
                    padding: 12px 20px;
                    color: #e0e0e0;
                    font-family: 'Inter', sans-serif;
                    font-size: 1.1rem;
                    text-align: center;
                    letter-spacing: 0.1em;
                    border-radius: 10px;
                    transition: all 0.3s;
                }
                .code-input:focus {
                    border-color: #8b0000;
                    background: rgba(0,0,0,0.7);
                    box-shadow: 0 0 15px rgba(139, 0, 0, 0.2);
                    outline: none;
                }
                .gothic-btn {
                    background: linear-gradient(135deg, #8b0000, #5a0000);
                    color: #e0e0e0;
                    border: none;
                    padding: 12px 25px;
                    font-weight: 700;
                    border-radius: 10px;
                    text-transform: uppercase;
                    transition: all 0.3s;
                    font-size: 0.85rem;
                    box-shadow: 0 4px 15px rgba(139, 0, 0, 0.3);
                    cursor: pointer;
                    white-space: nowrap;
                }
                .gothic-btn:hover { 
                    transform: translateY(-2px); 
                    box-shadow: 0 6px 20px rgba(139, 0, 0, 0.4);
                    filter: brightness(1.1);
                }
                .gothic-btn:active { transform: translateY(0); }

                .animate-fade-in { animation: fadeIn 0.4s ease-out; }
                @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
                .gothic-table.compact th,
                .gothic-table.compact td {
                    padding: 8px 12px;
                    font-size: 0.85rem;
                }
                .gothic-table.compact .actions-group .action-btn {
                    width: 28px;
                    height: 28px;
                    font-size: 0.8rem;
                }
                
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .success-pulse {
                    animation: successPulse 2s cubic-bezier(0.4, 0, 0.2, 1);
                }
                @keyframes successPulse {
                    0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(57, 230, 0, 0.4); }
                    10% { transform: scale(1.05); box-shadow: 0 0 0 10px rgba(57, 230, 0, 0); }
                    20% { transform: scale(1); }
                    100% { transform: scale(1); }
                }
            `}</style>
        </div>
    );
};

export default PlayerManagement;
