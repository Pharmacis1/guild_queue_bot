import React, { useState, useEffect } from 'react';

interface UserLimit {
    id: number;
    username: string;
    display_name: string;
    personal_limit: number;
}

interface PlayerSuggestion {
    nickname: string;
    class_id: number;
    has_telegram: boolean;
    user_id: number | null;
    role_id: number;
}

export default function LimitsManager() {
    const [defaultLimit, setDefaultLimit] = useState('1');
    const [loading, setLoading] = useState(true);
    const [overrides, setOverrides] = useState<UserLimit[]>([]);
    
    // Search state
    const [searchQuery, setSearchQuery] = useState('');
    const [suggestions, setSuggestions] = useState<PlayerSuggestion[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [isSearching, setIsSearching] = useState(false);
    
    // Selection state
    const [selectedPlayer, setSelectedPlayer] = useState<PlayerSuggestion | null>(null);
    const [newLimit, setNewLimit] = useState('1');
    const [savingLimit, setSavingLimit] = useState(false);
    const [savingDefault, setSavingDefault] = useState(false);

    const fetchData = async () => {
        setLoading(true);
        try {
            const sRes = await fetch('/api/master/settings');
            const sData = await sRes.json();
            if (sData.status === 'ok') {
                setDefaultLimit(sData.settings.default_limit);
            }

            const oRes = await fetch('/api/master/user_limits');
            const oData = await oRes.json();
            if (oData.status === 'ok') {
                setOverrides(oData.users);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    // Suggestions logic
    useEffect(() => {
        const delayDebounceFn = setTimeout(async () => {
            if (searchQuery.trim().length >= 2) {
                setIsSearching(true);
                try {
                    const res = await fetch('/api/master/search_players', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query: searchQuery.trim() })
                    });
                    const data = await res.json();
                    if (data.status === 'ok') {
                        setSuggestions(data.players);
                        setShowSuggestions(true);
                    }
                } catch (e) {
                    console.error(e);
                } finally {
                    setIsSearching(false);
                }
            } else {
                setSuggestions([]);
                setShowSuggestions(false);
            }
        }, 300);

        return () => clearTimeout(delayDebounceFn);
    }, [searchQuery]);

    const saveDefault = async () => {
        setSavingDefault(true);
        try {
            await fetch('/api/master/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ default_limit: defaultLimit })
            });
        } catch (e) {
            console.error(e);
        } finally {
            setSavingDefault(false);
        }
    };

    const setUserLimit = async (userId: number | null, roleId: number | null, limit: number | null) => {
        setSavingLimit(true);
        try {
            const res = await fetch('/api/master/user_limit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, role_id: roleId, limit })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                fetchData();
                setSelectedPlayer(null);
                setSearchQuery('');
            } else {
                alert(data.message);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setSavingLimit(false);
        }
    };

    const selectPlayer = (p: PlayerSuggestion) => {
        setSelectedPlayer(p);
        setShowSuggestions(false);
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '40px' }}>
            <div>
                <h2 style={{ color: '#ccc', fontFamily: "'Cinzel', serif", margin: '0 0 15px 0' }}>⚙️ Общие лимиты</h2>
                <div style={{ background: '#151517', border: '1px solid #222', padding: '25px', borderRadius: '12px', display: 'flex', alignItems: 'center', gap: '20px' }}>
                    <div style={{ flex: 1 }}>
                        <div style={{ color: '#ccc', fontWeight: 'bold', marginBottom: '5px' }}>Лимит записей по умолчанию</div>
                        <div style={{ color: '#888', fontSize: '0.85rem' }}>Максимальное кол-во очередей, в которые может записаться игрок.</div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <input 
                            type="number" 
                            value={defaultLimit}
                            onChange={e => setDefaultLimit(e.target.value)}
                            style={{ width: '80px', background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px', borderRadius: '6px', textAlign: 'center' }}
                        />
                        <button 
                            onClick={saveDefault}
                            disabled={savingDefault}
                            style={{ 
                                background: '#8B0000', 
                                border: 'none', 
                                color: '#ddd', 
                                padding: '10px 25px', 
                                borderRadius: '6px', 
                                cursor: savingDefault ? 'wait' : 'pointer',
                                fontWeight: 'bold'
                            }}
                        >
                            {savingDefault ? '...' : 'OK'}
                        </button>
                    </div>
                </div>
            </div>

            <div>
                <h2 style={{ color: '#ddd', fontFamily: "'Cinzel', serif", margin: '0 0 15px 0' }}>👤 Индивидуальные лимиты</h2>
                <div style={{ background: '#151517', border: '1px solid #222', padding: '25px', borderRadius: '12px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <p style={{ color: '#888', margin: 0, fontSize: '0.9rem' }}>
                        Вы можете установить персональный лимит для конкретного игрока. Это значение будет приоритетнее общего лимита.
                    </p>

                    {/* Search Section */}
                    <div style={{ position: 'relative', width: '100%', maxWidth: '100%' }}>
                        <div style={{ display: 'flex', gap: '10px', width: '100%' }}>
                            <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
                                <input 
                                    type="text"
                                    placeholder="Поиск игрока (Ник)..."
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    style={{
                                        width: '100%',
                                        background: '#0a0a0a',
                                        border: '1px solid #333',
                                        color: '#ddd',
                                        padding: '12px 15px',
                                        borderRadius: '8px',
                                        fontSize: '0.9rem',
                                        outline: 'none',
                                        boxSizing: 'border-box'
                                    }}
                                />
                                {showSuggestions && suggestions.length > 0 && (
                                    <div style={{
                                        position: 'absolute',
                                        top: 'calc(100% + 5px)',
                                        left: 0,
                                        right: 0,
                                        backgroundColor: '#1a1a1a',
                                        border: '1px solid #444',
                                        borderRadius: '6px',
                                        zIndex: 100,
                                        maxHeight: '250px',
                                        overflowY: 'auto',
                                        boxShadow: '0 10px 30px rgba(0,0,0,0.8)'
                                    }}>
                                        {suggestions.map((p, idx) => (
                                            <div 
                                                key={idx}
                                                onClick={() => selectPlayer(p)}
                                                style={{
                                                    padding: '12px 15px',
                                                    cursor: 'pointer',
                                                    borderBottom: idx === suggestions.length - 1 ? 'none' : '1px solid #222',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '12px'
                                                }}
                                                onMouseOver={e => e.currentTarget.style.backgroundColor = '#2a2a2e'}
                                                onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                            >
                                                <img src={`/icons/${p.class_id}.png`} alt="" style={{ width: '22px', height: '22px', borderRadius: '3px' }} onError={(e) => e.currentTarget.src='/icons/0.png'} />
                                                <span style={{ color: '#ddd', fontSize: '0.9rem' }}>{p.nickname}</span>
                                                {!p.has_telegram && <span style={{ fontSize: '0.7rem', color: '#666', marginLeft: 'auto' }}>offline</span>}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        {selectedPlayer && (
                            <div style={{ 
                                marginTop: '15px', 
                                background: '#0a0a0a', 
                                border: '1px solid #8B0000', 
                                padding: '15px', 
                                borderRadius: '8px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                animation: 'fadeIn 0.3s ease'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                    <img src={`/icons/${selectedPlayer.class_id}.png`} alt="" style={{ width: '28px', height: '28px' }} onError={(e) => e.currentTarget.src='/icons/0.png'} />
                                    <div>
                                        <div style={{ color: '#ddd', fontWeight: 'bold' }}>{selectedPlayer.nickname}</div>
                                        <div style={{ color: '#666', fontSize: '0.75rem' }}>Установить персональный лимит</div>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                                    <input 
                                        type="number" 
                                        value={newLimit}
                                        onChange={e => setNewLimit(e.target.value)}
                                        style={{ width: '70px', background: '#111', border: '1px solid #333', color: '#ddd', padding: '8px', borderRadius: '4px', textAlign: 'center' }}
                                    />
                                    <button 
                                        onClick={() => setUserLimit(selectedPlayer.user_id, selectedPlayer.role_id, parseInt(newLimit))}
                                        disabled={savingLimit}
                                        style={{ background: '#8B0000', color: '#fff', border: 'none', padding: '8px 15px', borderRadius: '4px', fontWeight: 'bold', cursor: 'pointer' }}
                                    >
                                        УСТАНОВИТЬ
                                    </button>
                                    <button 
                                        onClick={() => setSelectedPlayer(null)}
                                        style={{ background: 'transparent', color: '#555', border: '1px solid #333', padding: '8px 12px', borderRadius: '4px', cursor: 'pointer' }}
                                    >
                                        ОТМЕНА
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Overrides Table */}
                    {overrides.length > 0 && (
                        <div style={{ marginTop: '20px' }}>
                            <h3 style={{ color: '#E0E0E0', fontSize: '1rem', marginBottom: '15px', borderBottom: '1px solid #222', paddingBottom: '10px' }}>
                                Действующие ограничения
                            </h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                {overrides.map(u => (
                                    <div key={u.id} style={{ 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        gap: '15px', 
                                        background: 'rgba(0,0,0,0.3)', 
                                        padding: '10px 15px', 
                                        borderRadius: '6px',
                                        border: '1px solid #222'
                                    }}>
                                        <div style={{ flex: 1 }}>
                                            <span style={{ color: '#88B0D3', fontWeight: 'bold' }}>{u.display_name}</span>
                                            <span style={{ color: '#555', fontSize: '0.8rem', marginLeft: '10px' }}>@{u.username}</span>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                                            <div style={{ color: '#fff', background: '#333', padding: '2px 10px', borderRadius: '10px', fontSize: '0.85rem' }}>
                                                Лимит: {u.personal_limit}
                                            </div>
                                            <button 
                                                onClick={() => setUserLimit(u.id, null, null)}
                                                style={{ background: 'none', border: 'none', color: '#ff4d4d', cursor: 'pointer', fontSize: '1rem' }}
                                                title="Сбросить лимит"
                                            >
                                                🗑️
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
