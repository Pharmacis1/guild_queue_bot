import React, { useState, useEffect } from 'react';
import { UserData } from '@/lib/api';
import LimitsManager from './management/LimitsManager';
import ConditionsManager from './management/ConditionsManager';
import LockManager from './management/LockManager';
import HistoryManager from './management/HistoryManager';

interface RewardDistributionProps {
    currentUser?: UserData | null;
    onBack?: () => void;
}

interface QueueInfo {
    id: number;
    name: string;
    count: number;
    is_locked: boolean;
    description: string;
}

type MgmtView = 'queue' | 'limits' | 'conditions' | 'lock' | 'history';

export default function RewardDistribution({ currentUser, onBack }: RewardDistributionProps) {
    const [queues, setQueues] = useState<QueueInfo[]>([]);
    const [pendingNotifications, setPendingNotifications] = useState<number>(0);
    const [selectedQueue, setSelectedQueue] = useState<QueueInfo | null>(null);
    const [entries, setEntries] = useState<QueueEntry[]>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [actionLoading, setActionLoading] = useState<number | null>(null);
    const [newPlayerName, setNewPlayerName] = useState("");
    const [draggedItem, setDraggedItem] = useState<number | null>(null);
    const [suggestions, setSuggestions] = useState<any[]>([]);
    const [searchClassId, setSearchClassId] = useState<number>(-1);
    const [showSuggestions, setShowSuggestions] = useState<boolean>(false);
    const [isSearching, setIsSearching] = useState<boolean>(false);
    const [view, setView] = useState<MgmtView>('queue');
    const [autoRequeue, setAutoRequeue] = useState<boolean>(false);
    const [copiedId, setCopiedId] = useState<number | null>(null);

    const fetchQueues = async () => {
        setLoading(true);
        try {
            const res = await fetch('/api/master/queues');
            const data = await res.json();
            if (data.status === 'ok') {
                setQueues(data.queues);
                setPendingNotifications(data.pending_notifications);
            } else {
                alert(`Ошибка: ${data.message}`);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchQueues();
    }, []);

    const fetchEntries = async (queue: QueueInfo) => {
        setLoading(true);
        setSelectedQueue(queue);
        try {
            const res = await fetch('/api/master/queue_entries', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ queue_id: queue.id })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                setEntries(data.entries);
            } else {
                alert(`Ошибка: ${data.message}`);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleAction = async (entryId: number, action: 'issue' | 'warn' | 'remove') => {
        if (!currentUser?.id) return;
        
        if (action === 'remove' && !confirm("Удалить игрока из очереди?")) return;

        setActionLoading(entryId);
        let endpoint = '';
        if (action === 'issue') endpoint = 'issue_reward';
        else if (action === 'warn') endpoint = 'warn_user';
        else if (action === 'remove') endpoint = 'remove_from_queue';
        
        try {
            const res = await fetch(`/api/master/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entry_id: entryId, master_id: currentUser.id })
            });
            const data = await res.json();
            
            if (data.status === 'ok' || data.status === 'error') {
                if (data.status === 'error') alert(data.message);
                if (data.status === 'ok') {
                    if (selectedQueue) fetchEntries(selectedQueue);
                }
            }
        } catch (e) {
            console.error(e);
        } finally {
            setActionLoading(null);
        }
    };

    const addPlayer = async () => {
        if (!selectedQueue || !newPlayerName.trim()) return;
        setLoading(true);
        try {
            const res = await fetch('/api/master/add_to_queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    queue_id: selectedQueue.id, 
                    character_name: newPlayerName.trim(),
                    auto_requeue: autoRequeue
                })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                setNewPlayerName("");
                setAutoRequeue(false);
                fetchEntries(selectedQueue);
                fetchQueues();
            } else {
                alert(data.message);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const handleCopy = (nick: string, id: number) => {
        navigator.clipboard.writeText(nick);
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
    };

    const handleDragStart = (e: React.DragEvent, id: number) => {
        setDraggedItem(id);
        e.dataTransfer.effectAllowed = 'move';
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    };

    const handleDrop = async (e: React.DragEvent, targetId: number) => {
        e.preventDefault();
        if (draggedItem === null || draggedItem === targetId) return;

        const newEntries = [...entries];
        const draggedIdx = newEntries.findIndex(item => item.id === draggedItem);
        const targetIdx = newEntries.findIndex(item => item.id === targetId);
        
        const [movedItem] = newEntries.splice(draggedIdx, 1);
        newEntries.splice(targetIdx, 0, movedItem);
        
        setEntries(newEntries);
        setDraggedItem(null);

        // Update backend
        try {
            await fetch('/api/master/reorder_queue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    queue_id: selectedQueue?.id, 
                    entry_ids: newEntries.map(it => it.id) 
                })
            });
        } catch (err) {
            console.error(err);
        }
    };

    // New useEffect for searching players
    useEffect(() => {
        const delayDebounceFn = setTimeout(async () => {
            const trimmedName = newPlayerName.trim();
            // Show suggestions if name >= 2 chars OR if a specific class is selected
            if (trimmedName.length >= 2 || (searchClassId !== -1)) {
                setIsSearching(true);
                try {
                    const res = await fetch('/api/master/search_players', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query: trimmedName, class_id: searchClassId })
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
    }, [newPlayerName, searchClassId]);

    const selectPlayer = (nick: string) => {
        setNewPlayerName(nick);
        setShowSuggestions(false);
    };

    const classes = [
        { id: 0, name: "Воин" }, { id: 1, name: "Маг" }, { id: 2, name: "Шаман" }, { id: 3, name: "Друид" },
        { id: 4, name: "Оборотень" }, { id: 5, name: "Убийца" }, { id: 6, name: "Лучник" }, { id: 7, name: "Жрец" },
        { id: 8, name: "Страж" }, { id: 9, name: "Мистик" }, { id: 10, name: "Призрак" }, { id: 11, name: "Жнец" },
        { id: 12, name: "Стрелок" }, { id: 13, name: "Паладин" }, { id: 14, name: "Странник" }, { id: 15, name: "Бард" },
        { id: 16, name: "Дух крови" }
    ];

    const sendNotifications = async () => {
        if (!confirm("Отправить уведомления всем игрокам?")) return;
        
        try {
            const res = await fetch('/api/master/send_notifications', { method: 'POST' });
            const data = await res.json();
            alert(data.message);
            if (data.status === 'ok') fetchQueues();
        } catch (e) {
            console.error(e);
        }
    };


    const getColorForInitial = (initial: string) => {
        const colors = ['#a25ed5', '#24a1cf', '#d69e2e', '#4a5568', '#f56565', '#48bb78', '#ed8936', '#9f7aea', '#ed64a6'];
        const charCode = initial.charCodeAt(0);
        return colors[charCode % colors.length];
    };

    const queueIconMap: { [key: string]: string } = {
        "Жемчужины Фу Си": "fuxi_pearls.png",
        "Знаки Единства": "unity_signs.png",
        "Колода карт": "card_deck.png",
        "Сущность карты": "card_essence.png",
        "Камень божества": "deity_stone.png",
        "Цилинь": "qilin.png",
        "Драконья чешуя": "dragon_scale.png"
    };

    interface QueueEntry {
        id: number;
        character_name: string;
        valor: number;
        is_afk: boolean;
        auto_requeue: boolean;
        class_id: number;
    }

    return (
        <div style={{ display: 'flex', backgroundColor: '#0a0a0a', borderRadius: '12px', border: '1px solid #222' }}>
            {/* Left Sidebar - Queues (Resources) */}
            <div style={{ 
                width: '280px', 
                backgroundColor: '#0d0d0d', 
                borderRight: '1px solid #222', 
                display: 'flex', 
                flexDirection: 'column',
                transition: 'all 0.3s ease-in-out'
            }}>
                {/* Back Button in Sidebar */}
                <div style={{ padding: '10px 15px', borderBottom: '1px solid #222' }}>
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
                            fontSize: '0.9rem',
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

                <div className="no-scrollbar" style={{ padding: '20px 0' }}>
                    <h3 style={{ 
                        color: '#ccc', 
                        fontSize: '1rem', 
                        fontFamily: "'Cinzel', serif", 
                        letterSpacing: '1px', 
                        marginLeft: '20px', 
                        marginBottom: '20px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px'
                    }}>
                        <div style={{ width: '3px', height: '20px', backgroundColor: '#ff4d6d' }}></div>
                        РЕСУРСЫ
                    </h3>

                    {loading && queues.length === 0 ? (
                        <div style={{ padding: '20px', color: '#666', textAlign: 'center' }}>Загрузка...</div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', padding: '0 10px' }}>
                            {queues.map(q => {
                                const isSelected = selectedQueue?.id === q.id;
                                const iconFile = queueIconMap[q.name];
                                return (
                                    <div 
                                        key={q.id}
                                        onClick={() => { fetchEntries(q); setView('queue'); }}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '12px',
                                            padding: '12px 15px',
                                            cursor: 'pointer',
                                            backgroundColor: isSelected ? 'rgba(255, 77, 109, 0.05)' : '#111',
                                            border: isSelected ? '1px solid rgba(255, 77, 109, 0.4)' : '1px solid #222',
                                            borderRadius: '6px',
                                            transition: 'all 0.2s',
                                            position: 'relative',
                                            color: isSelected ? '#ff4d6d' : '#ccc'
                                        }}
                                        onMouseOver={(e) => {
                                            if (!isSelected) {
                                                e.currentTarget.style.borderColor = '#444';
                                                e.currentTarget.style.backgroundColor = '#151515';
                                            }
                                        }}
                                        onMouseOut={(e) => {
                                            if (!isSelected) {
                                                e.currentTarget.style.borderColor = '#222';
                                                e.currentTarget.style.backgroundColor = '#111';
                                            }
                                        }}
                                    >
                                        {iconFile ? (
                                             <img 
                                                src={`/icons/queues/${iconFile}`} 
                                                alt={q.name}
                                                style={{ 
                                                    width: '28px', 
                                                    height: '28px', 
                                                    borderRadius: '4px',
                                                    border: isSelected ? '1px solid #ff4d6d' : '1px solid #333',
                                                    boxShadow: isSelected ? '0 0 8px rgba(255, 77, 109, 0.3)' : 'none'
                                                }}
                                            />
                                        ) : (
                                            <div style={{ 
                                                width: '24px', 
                                                height: '24px', 
                                                borderRadius: '50%', 
                                                backgroundColor: isSelected ? '#fff' : getColorForInitial(q.name),
                                                display: 'flex',
                                                justifyContent: 'center',
                                                alignItems: 'center',
                                                fontSize: '12px',
                                                boxShadow: isSelected ? '0 0 10px rgba(255, 255, 255, 0.5)' : 'none'
                                            }}>
                                            </div>
                                        )}
                                        
                                        <span style={{ fontSize: '0.9rem', fontWeight: isSelected ? '600' : '400' }}>{q.name}</span>
                                        
                                        <span style={{ 
                                            marginLeft: 'auto', 
                                            fontSize: '0.75rem', 
                                            color: isSelected ? '#ff4d6d' : '#666',
                                            opacity: 0.8
                                        }}>
                                            {q.count} чел.
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
                
                {pendingNotifications > 0 && (
                     <div style={{ padding: '15px', borderTop: '1px solid #222', backgroundColor: '#0a0a0a' }}>
                        <button 
                            onClick={sendNotifications}
                            style={{ 
                                width: '100%',
                                background: 'rgba(139, 0, 0, 0.1)',
                                border: '1px solid #8B0000',
                                color: '#ff4d4d',
                                padding: '12px',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                fontSize: '0.8rem',
                                textTransform: 'uppercase',
                                transition: 'all 0.2s',
                                fontWeight: 'bold'
                            }}
                            onMouseOver={(e) => {
                                e.currentTarget.style.backgroundColor = 'rgba(139, 0, 0, 0.3)';
                                e.currentTarget.style.boxShadow = '0 0 15px rgba(139, 0, 0, 0.3)';
                            }}
                            onMouseOut={(e) => {
                                e.currentTarget.style.backgroundColor = 'rgba(139, 0, 0, 0.1)';
                                e.currentTarget.style.boxShadow = 'none';
                            }}
                        >
                            🔔 Уведомить ({pendingNotifications})
                        </button>
                    </div>
                )}

                <div className="no-scrollbar" style={{ padding: '20px 0', borderTop: '1px solid #222' }}>
                    <h3 style={{ 
                        color: '#ccc', 
                        fontSize: '1rem', 
                        fontFamily: "'Cinzel', serif", 
                        letterSpacing: '1px', 
                        marginLeft: '20px', 
                        marginBottom: '20px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px'
                    }}>
                        <div style={{ width: '3px', height: '20px', backgroundColor: '#8B0000' }}></div>
                        УПРАВЛЕНИЕ
                    </h3>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', padding: '0 10px' }}>
                        {[
                            { id: 'limits', name: 'Лимиты', icon: '⚙️' },
                            { id: 'conditions', name: 'Условия', icon: '📝' },
                            { id: 'lock', name: 'Блокировка', icon: '🔒' },
                            { id: 'history', name: 'История', icon: '📜' }
                        ].map(item => {
                            const isSelected = view === item.id;
                            return (
                                <div 
                                    key={item.id}
                                    onClick={() => { setView(item.id as MgmtView); setSelectedQueue(null); }}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '12px',
                                        padding: '12px 15px',
                                        cursor: 'pointer',
                                        backgroundColor: isSelected ? 'rgba(139, 0, 0, 0.1)' : 'transparent',
                                        border: isSelected ? '1px solid #8B0000' : '1px solid transparent',
                                        borderRadius: '6px',
                                        transition: 'all 0.2s',
                                        color: isSelected ? '#ff4d6d' : '#888'
                                    }}
                                    onMouseOver={(e) => {
                                        if (!isSelected) {
                                            e.currentTarget.style.backgroundColor = '#151515';
                                            e.currentTarget.style.color = '#fff';
                                        }
                                    }}
                                    onMouseOut={(e) => {
                                        if (!isSelected) {
                                            e.currentTarget.style.backgroundColor = 'transparent';
                                            e.currentTarget.style.color = '#888';
                                        }
                                    }}
                                >
                                    <span style={{ fontSize: '1.2rem' }}>{item.icon}</span>
                                    <span style={{ fontSize: '0.9rem', fontWeight: isSelected ? '600' : '400' }}>{item.name}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Main Content Area */}
            <div className="no-scrollbar" style={{ flex: 1, padding: '30px', display: 'flex', flexDirection: 'column', backgroundColor: '#0f0f11', minHeight: '800px' }}>
                {view !== 'queue' ? (
                    <div style={{ maxWidth: '1000px', width: '100%', margin: '0 auto' }}>
                        {view === 'limits' && <LimitsManager />}
                        {view === 'conditions' && <ConditionsManager />}
                        {view === 'lock' && <LockManager />}
                        {view === 'history' && <HistoryManager />}
                    </div>
                ) : !selectedQueue ? (
                    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#555', flexDirection: 'column', gap: '15px' }}>
                        <div style={{ fontSize: '4rem', opacity: 0.2 }}>🎁</div>
                        <p style={{ fontFamily: "'Cinzel', serif", fontSize: '1.2rem', letterSpacing: '1px' }}>Выберите ресурс в списке слева</p>
                    </div>
                ) : (
                    <div style={{ maxWidth: '900px', width: '100%', margin: '0 auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '30px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                                <div>
                                    <h2 style={{ 
                                        color: '#eee', 
                                        margin: '0 0 10px 0',
                                        fontSize: '1.5rem',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '10px'
                                    }}>
                                        🎁 Раздача: {selectedQueue.name}
                                    </h2>
                                    <p style={{ color: '#888', fontSize: '0.85rem', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <span style={{ color: '#ff4d6d', fontSize: '1.2rem' }}>📌</span> 
                                        Нажми на кнопку "Выдать", после того как отправишь награду в игре.
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Table Header & Add Player */}
                        <div style={{ 
                            display: 'flex', 
                            flexDirection: 'column',
                            gap: '12px',
                            marginBottom: '20px',
                            background: '#151517',
                            padding: '15px',
                            borderRadius: '12px',
                            border: '1px solid #222',
                            boxShadow: '0 4px 20px rgba(0,0,0,0.3)'
                        }}>
                             <div style={{ 
                                 display: 'flex', 
                                 flexFlow: 'row nowrap',
                                 gap: '12px', 
                                 alignItems: 'center',
                                 width: '100%'
                             }}>
                                {/* Nickname search with Suggestions */}
                                <div style={{ 
                                    position: 'relative', 
                                    flex: '1 1 0%', // Force it to start from zero and grow
                                    minWidth: 0,
                                    width: '100%'
                                }}>
                                    <input 
                                        type="text" 
                                        placeholder="Ник игрока..."
                                        value={newPlayerName}
                                        onChange={(e) => setNewPlayerName(e.target.value)}
                                        onFocus={() => { if(suggestions.length > 0) setShowSuggestions(true); }}
                                        style={{
                                            width: '100%',
                                            background: '#0a0a0a',
                                            border: '1px solid #333',
                                            color: '#ddd',
                                            padding: '10px 14px',
                                            borderRadius: '6px',
                                            fontSize: '0.9rem',
                                            transition: 'border-color 0.2s',
                                            outline: 'none',
                                            boxSizing: 'border-box'
                                        }}
                                        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
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
                                            zIndex: 9999,
                                            maxHeight: '250px',
                                            overflowY: 'auto',
                                            boxShadow: '0 10px 30px rgba(0,0,0,0.8)'
                                        }}>
                                            {suggestions.map((p, idx) => (
                                                <div 
                                                    key={idx}
                                                    onClick={() => selectPlayer(p.nickname)}
                                                    style={{
                                                        padding: '12px 14px',
                                                        cursor: 'pointer',
                                                        borderBottom: idx === suggestions.length - 1 ? 'none' : '1px solid #222',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '12px'
                                                    }}
                                                    onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#2a2a2e'}
                                                    onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                                                >
                                                    <img src={`/icons/${p.class_id}.png`} alt="" style={{ width: '22px', height: '22px', borderRadius: '3px' }} onError={(e) => e.currentTarget.src='/icons/0.png'} />
                                                    <span style={{ color: '#ccc', fontSize: '0.9rem', fontWeight: 500 }}>{p.nickname}</span>
                                                    {!p.has_telegram && <span style={{ fontSize: '0.65rem', color: '#666', marginLeft: 'auto' }}>offline</span>}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Class Filter */}
                                <div style={{ 
                                    display: 'flex', 
                                    gap: '8px', 
                                    alignItems: 'center', 
                                    backgroundColor: '#0a0a0a', 
                                    paddingLeft: '12px',
                                    borderRadius: '6px', 
                                    border: '1px solid #333',
                                    minWidth: '160px',
                                    flex: '0 0 auto',
                                    whiteSpace: 'nowrap'
                                }}>
                                    <span style={{ fontSize: '0.75rem', color: '#555' }}>Профа:</span>
                                    <select 
                                        value={searchClassId}
                                        onChange={(e) => setSearchClassId(Number(e.target.value))}
                                        style={{
                                            background: '#0a0a0a',
                                            border: 'none',
                                            color: '#aaa',
                                            padding: '10px 8px',
                                            fontSize: '0.85rem',
                                            cursor: 'pointer',
                                            outline: 'none',
                                            borderRadius: '6px'
                                        }}
                                    >
                                        <option value={-1} style={{ background: '#1a1a1a', color: '#fff' }}>Все</option>
                                        {classes.map(c => (
                                            <option key={c.id} value={c.id} style={{ background: '#111', color: '#fff' }}>{c.name}</option>
                                        ))}
                                    </select>
                                </div>

                                {/* Auto-requeue Checkbox */}
                                <label style={{ 
                                    display: 'flex', 
                                    alignItems: 'center', 
                                    gap: '8px', 
                                    cursor: 'pointer',
                                    padding: '8px 12px',
                                    backgroundColor: '#0a0a0a',
                                    borderRadius: '6px',
                                    border: '1px solid #333',
                                    userSelect: 'none',
                                    minWidth: '85px',
                                    flex: '0 0 auto',
                                    whiteSpace: 'nowrap'
                                }}>
                                    <input 
                                        type="checkbox" 
                                        checked={autoRequeue}
                                        onChange={(e) => setAutoRequeue(e.target.checked)}
                                        style={{ cursor: 'pointer', accentColor: '#8B0000' }}
                                    />
                                    <span style={{ fontSize: '0.85rem', color: '#aaa' }}>Авто</span>
                                </label>

                                {/* Add Button */}
                                <button
                                    onClick={addPlayer}
                                    style={{
                                        background: 'linear-gradient(135deg, #8B0000 0%, #4B0000 100%)',
                                        border: '1px solid #ff4d6d33',
                                        color: '#eee',
                                        padding: '10px 24px',
                                        borderRadius: '6px',
                                        cursor: 'pointer',
                                        fontWeight: 'bold',
                                        fontSize: '0.85rem',
                                        letterSpacing: '0.5px',
                                        boxShadow: '0 2px 10px rgba(139, 0, 0, 0.4)',
                                        transition: 'all 0.2s',
                                        width: '120px',
                                        flex: '0 0 auto'
                                    }}
                                    onMouseOver={(e) => {
                                        e.currentTarget.style.boxShadow = '0 0 20px rgba(255, 77, 109, 0.5)';
                                        e.currentTarget.style.transform = 'translateY(-2px)';
                                    }}
                                    onMouseOut={(e) => {
                                        e.currentTarget.style.boxShadow = '0 2px 10px rgba(139, 0, 0, 0.4)';
                                        e.currentTarget.style.transform = 'translateY(0)';
                                    }}
                                >
                                    ДОБАВИТЬ
                                </button>
                             </div>
                        </div>

                        <div style={{ 
                            display: 'grid', 
                            gridTemplateColumns: '50px 40px minmax(180px, 2fr) 100px 80px 180px', 
                            padding: '10px 15px',
                            borderBottom: '1px solid #333',
                            color: '#ff4d6d',
                            fontSize: '0.75rem',
                            textTransform: 'uppercase',
                            letterSpacing: '1px',
                            fontWeight: 'bold',
                            marginBottom: '10px'
                        }}>
                            <div style={{ textAlign: 'center' }}>№</div>
                            <div></div>
                            <div>Ник Игрока</div>
                            <div style={{ textAlign: 'center' }}>Доблесть</div>
                            <div style={{ textAlign: 'center' }} title="Автозапись в очередь">Авто</div>
                            <div style={{ textAlign: 'right' }}>Действия</div>
                        </div>

                        {/* Entries List */}
                        <div style={{ flex: 1, paddingRight: '5px' }}>
                            {loading && entries.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>Загрузка списка...</div>
                            ) : entries.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '60px', color: '#555' }}>
                                    Очередь пуста
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                    {entries.map((e, index) => {
                                        const isDragged = draggedItem === e.id;
                                        return (
                                            <div 
                                                key={e.id} 
                                                draggable
                                                onDragStart={(ev) => handleDragStart(ev, e.id)}
                                                onDragOver={handleDragOver}
                                                onDrop={(ev) => handleDrop(ev, e.id)}
                                                style={{
                                                    display: 'grid',
                                                    gridTemplateColumns: '50px 40px minmax(180px, 2fr) 100px 80px 180px',
                                                    alignItems: 'center',
                                                    backgroundColor: isDragged ? '#222' : 'transparent',
                                                    borderBottom: '1px solid #1a1a1a',
                                                    padding: '8px 15px',
                                                    transition: 'all 0.2s',
                                                    cursor: 'grab',
                                                    opacity: isDragged ? 0.5 : 1,
                                                    borderRadius: '4px'
                                                }}
                                                onMouseOver={(ev) => { if(!isDragged) ev.currentTarget.style.backgroundColor = '#151515'; }}
                                                onMouseOut={(ev) => { if(!isDragged) ev.currentTarget.style.backgroundColor = 'transparent'; }}
                                            >
                                                {/* Position Number */}
                                                <div style={{ 
                                                    textAlign: 'center', 
                                                    color: '#555', 
                                                    fontWeight: 'bold',
                                                    fontSize: '0.8rem',
                                                    fontFamily: "'Cinzel', serif"
                                                }}>
                                                    #{index + 1}
                                                </div>

                                                {/* Profession Icon */}
                                                <div style={{ display: 'flex', justifyContent: 'center' }}>
                                                    {e.class_id !== -1 ? (
                                                        <img 
                                                            src={`/icons/${e.class_id}.png`} 
                                                            alt="class" 
                                                            onError={(ev) => { ev.currentTarget.src = '/icons/0.png' }}
                                                            style={{ width: '24px', height: '24px', borderRadius: '4px', border: '1px solid #333' }}
                                                        />
                                                    ) : (
                                                        <div style={{ width: '24px', height: '24px', backgroundColor: '#222', borderRadius: '4px', border: '1px solid #333' }}></div>
                                                    )}
                                                </div>

                                                {/* Player Info */}
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', userSelect: 'text' }}>
                                                    <span 
                                                        style={{ color: '#88B0D3', fontSize: '0.95rem', fontWeight: '500', cursor: 'text' }}
                                                        onMouseDown={(ev) => ev.stopPropagation()}
                                                    >
                                                        {e.character_name}
                                                    </span>
                                                    {e.is_afk && <span style={{ backgroundColor: '#2a2010', color: '#ffaa00', padding: '2px 4px', borderRadius: '4px', fontSize: '0.65rem' }}>AFK</span>}
                                                    
                                                    {/* Small copy icon for extra UX */}
                                                     <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                                        <span 
                                                            title="Копировать ник"
                                                            onClick={(ev) => {
                                                                ev.stopPropagation();
                                                                handleCopy(e.character_name, e.id);
                                                            }}
                                                            style={{ cursor: 'pointer', fontSize: '0.8rem', opacity: 0.3, transition: 'opacity 0.2s' }}
                                                            onMouseOver={(ev) => ev.currentTarget.style.opacity = '1'}
                                                            onMouseOut={(ev) => ev.currentTarget.style.opacity = '0.3'}
                                                        >
                                                            📋
                                                        </span>
                                                        {copiedId === e.id && (
                                                            <div style={{
                                                                position: 'absolute',
                                                                left: '20px',
                                                                backgroundColor: '#48bb78',
                                                                color: '#fff',
                                                                padding: '2px 6px',
                                                                borderRadius: '4px',
                                                                fontSize: '0.65rem',
                                                                whiteSpace: 'nowrap',
                                                                zIndex: 10,
                                                                animation: 'fadeInOut 2s forwards'
                                                            }}>
                                                                Скопировано!
                                                            </div>
                                                        )}
                                                     </div>
                                                </div>

                                                {/* Valor */}
                                                <div style={{ textAlign: 'center', color: '#ddd', fontSize: '0.9rem', fontWeight: 'bold' }}>
                                                    {e.valor !== -1 ? e.valor : '0'}
                                                </div>

                                                {/* Auto-requeue */}
                                                <div style={{ textAlign: 'center' }}>
                                                    {e.auto_requeue ? (
                                                        <span style={{ color: '#48bb78', fontSize: '1.1rem' }} title="Автоматическая запись">✓</span>
                                                    ) : (
                                                        <span style={{ color: '#333', fontSize: '1rem' }}>—</span>
                                                    )}
                                                </div>

                                                {/* Actions */}
                                                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', alignItems: 'center' }}>
                                                    <button
                                                        onClick={() => handleAction(e.id, 'issue')}
                                                        disabled={actionLoading !== null}
                                                        style={{
                                                            background: 'linear-gradient(135deg, #8B0000 0%, #4B0000 100%)',
                                                            backdropFilter: 'blur(4px)',
                                                            border: '1px solid rgba(255, 255, 255, 0.1)',
                                                            color: '#eee',
                                                            padding: '5px 12px',
                                                            borderRadius: '4px',
                                                            cursor: actionLoading !== null ? 'wait' : 'pointer',
                                                            fontWeight: 'bold',
                                                            fontSize: '0.7rem',
                                                            textTransform: 'uppercase',
                                                            letterSpacing: '0.5px',
                                                            opacity: actionLoading !== null ? 0.5 : 1,
                                                            transition: 'all 0.2s',
                                                            boxShadow: '0 2px 10px rgba(0,0,0,0.3)'
                                                        }}
                                                        onMouseOver={(ev) => { 
                                                            if(actionLoading === null) {
                                                                ev.currentTarget.style.transform = 'scale(1.05)';
                                                                ev.currentTarget.style.boxShadow = '0 0 15px rgba(255, 77, 109, 0.4)';
                                                            }
                                                        }}
                                                        onMouseOut={(ev) => { 
                                                            if(actionLoading === null) {
                                                                ev.currentTarget.style.transform = 'scale(1)';
                                                                ev.currentTarget.style.boxShadow = '0 2px 10px rgba(0,0,0,0.3)';
                                                            }
                                                        }}
                                                    >
                                                        {actionLoading === e.id ? '...' : 'Выдать'}
                                                    </button>
                                                    
                                                    <button
                                                        onClick={() => handleAction(e.id, 'warn')}
                                                        disabled={actionLoading !== null}
                                                        title="Пропустить (условия не выполнены)"
                                                        style={{
                                                            background: 'rgba(184, 155, 61, 0.05)',
                                                            border: '1px solid #b89b3d',
                                                            color: '#b89b3d',
                                                            width: '26px',
                                                            height: '26px',
                                                            borderRadius: '4px',
                                                            cursor: 'pointer',
                                                            display: 'flex',
                                                            justifyContent: 'center',
                                                            alignItems: 'center',
                                                            fontSize: '0.9rem',
                                                            opacity: actionLoading !== null ? 0.5 : 1,
                                                            transition: 'all 0.2s'
                                                        }}
                                                    >!</button>

                                                    <button
                                                        onClick={() => handleAction(e.id, 'remove')}
                                                        disabled={actionLoading !== null}
                                                        title="Удалить из очереди"
                                                        style={{
                                                            background: 'rgba(255, 77, 77, 0.1)',
                                                            border: '1px solid #ff4d4d',
                                                            color: '#ff4d4d',
                                                            width: '26px',
                                                            height: '26px',
                                                            borderRadius: '4px',
                                                            cursor: 'pointer',
                                                            display: 'flex',
                                                            justifyContent: 'center',
                                                            alignItems: 'center',
                                                            fontSize: '0.9rem',
                                                            opacity: actionLoading !== null ? 0.5 : 1
                                                        }}
                                                    >🗑</button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
