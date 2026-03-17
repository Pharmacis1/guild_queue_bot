import React, { useState, useEffect, useRef } from 'react';

interface HistoryRecord {
    id: number;
    character_name: string;
    queue_name: string;
    issued_by: string;
    record_type: string;
    timestamp: string;
}

interface Suggestions {
    queues: string[];
    characters: string[];
    masters: string[];
}

export default function HistoryManager() {
    const [history, setHistory] = useState<HistoryRecord[]>([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(0);
    const [total, setTotal] = useState(0);
    const limit = 50;

    const [filters, setFilters] = useState({
        queue_name: '',
        character_name: '',
        issued_by: ''
    });

    const [suggestions, setSuggestions] = useState<Suggestions>({ queues: [], characters: [], masters: [] });
    const [activeSuggestionField, setActiveSuggestionField] = useState<string | null>(null);

    const fetchHistory = async () => {
        setLoading(true);
        try {
            const query = new URLSearchParams({
                limit: limit.toString(),
                offset: (page * limit).toString(),
                ...filters
            });
            const res = await fetch(`/api/master/reward_history?${query}`);
            const data = await res.json();
            if (data.status === 'ok') {
                setHistory(data.history);
                setTotal(data.total);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    const fetchSuggestions = async () => {
        try {
            const res = await fetch('/api/master/history_suggestions');
            const data = await res.json();
            if (data.status === 'ok') {
                setSuggestions({
                    queues: data.queues,
                    characters: data.characters,
                    masters: data.masters
                });
            }
        } catch (e) {
            console.error(e);
        }
    };

    useEffect(() => {
        fetchHistory();
    }, [page, filters]);

    useEffect(() => {
        fetchSuggestions();
    }, []);

    const handleDelete = async (id: number) => {
        if (!confirm("Удалить эту запись из истории?")) return;
        try {
            const res = await fetch(`/api/master/reward_history/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.status === 'ok') {
                fetchHistory();
                fetchSuggestions(); // Refresh unique values
            } else {
                alert(data.message);
            }
        } catch (e) {
            console.error(e);
        }
    };

    const renderSuggestions = (field: keyof typeof filters, list: string[]) => {
        if (activeSuggestionField !== field) return null;
        const filtered = list.filter(item => 
            item.toLowerCase().includes(filters[field].toLowerCase()) && 
            item.toLowerCase() !== filters[field].toLowerCase()
        ).slice(0, 10);

        if (filtered.length === 0) return null;

        return (
            <div style={{
                position: 'absolute',
                top: 'calc(100% + 5px)',
                left: 0,
                right: 0,
                backgroundColor: '#1a1a1a',
                border: '1px solid #444',
                borderRadius: '6px',
                zIndex: 100,
                maxHeight: '200px',
                overflowY: 'auto',
                boxShadow: '0 10px 30px rgba(0,0,0,0.8)'
            }}>
                {filtered.map((item, idx) => (
                    <div 
                        key={idx}
                        onClick={() => {
                            setFilters({ ...filters, [field]: item });
                            setActiveSuggestionField(null);
                        }}
                        style={{ padding: '10px 12px', cursor: 'pointer', borderBottom: '1px solid #222', color: '#ccc', fontSize: '0.85rem' }}
                        onMouseOver={e => e.currentTarget.style.backgroundColor = '#2a2a2e'}
                        onMouseOut={e => e.currentTarget.style.backgroundColor = 'transparent'}
                    >
                        {item}
                    </div>
                ))}
            </div>
        );
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <h2 style={{ color: '#ccc', fontFamily: "'Cinzel', serif", margin: 0 }}>📜 История выдачи</h2>
            
            <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: '20px', 
                background: '#151517', 
                padding: '24px', 
                borderRadius: '12px', 
                border: '1px solid #222' 
            }}>
                <div style={{ position: 'relative' }}>
                    <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '5px', marginLeft: '5px' }}>Очередь</div>
                    <input 
                        placeholder="Все очереди..." 
                        value={filters.queue_name}
                        onChange={e => setFilters({...filters, queue_name: e.target.value})}
                        onFocus={() => setActiveSuggestionField('queue_name')}
                        onBlur={() => setTimeout(() => setActiveSuggestionField(null), 200)}
                        style={{ background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px 14px', borderRadius: '6px', width: '100%', outline: 'none', boxSizing: 'border-box' }}
                    />
                    {renderSuggestions('queue_name', suggestions.queues)}
                </div>
                <div style={{ position: 'relative' }}>
                    <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '5px', marginLeft: '5px' }}>Ник игрока</div>
                    <input 
                        placeholder="Любой игрок..." 
                        value={filters.character_name}
                        onChange={e => setFilters({...filters, character_name: e.target.value})}
                        onFocus={() => setActiveSuggestionField('character_name')}
                        onBlur={() => setTimeout(() => setActiveSuggestionField(null), 200)}
                        style={{ background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px 14px', borderRadius: '6px', width: '100%', outline: 'none', boxSizing: 'border-box' }}
                    />
                    {renderSuggestions('character_name', suggestions.characters)}
                </div>
                <div style={{ position: 'relative' }}>
                    <div style={{ color: '#888', fontSize: '0.75rem', marginBottom: '5px', marginLeft: '5px' }}>Кто выдал</div>
                    <input 
                        placeholder="Любой мастер..." 
                        value={filters.issued_by}
                        onChange={e => setFilters({...filters, issued_by: e.target.value})}
                        onFocus={() => setActiveSuggestionField('issued_by')}
                        onBlur={() => setTimeout(() => setActiveSuggestionField(null), 200)}
                        style={{ background: '#0a0a0a', border: '1px solid #333', color: '#ddd', padding: '10px 14px', borderRadius: '6px', width: '100%', outline: 'none', boxSizing: 'border-box' }}
                    />
                    {renderSuggestions('issued_by', suggestions.masters)}
                </div>
            </div>

            <div className="table-wrapper" style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', color: '#ccc', fontSize: '0.9rem' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid #333', color: '#ff4d6d', textTransform: 'uppercase', fontSize: '0.7rem', letterSpacing: '1px' }}>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Дата</th>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Очередь</th>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Игрок</th>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Мастер</th>
                            <th style={{ padding: '12px', textAlign: 'left' }}>Тип</th>
                            <th style={{ padding: '12px', textAlign: 'right' }}>Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan={6} style={{ textAlign: 'center', padding: '20px' }}>Загрузка...</td></tr>
                        ) : history.length === 0 ? (
                            <tr><td colSpan={6} style={{ textAlign: 'center', padding: '20px' }}>Нет записей</td></tr>
                        ) : history.map(r => (
                            <tr key={r.id} style={{ borderBottom: '1px solid #1a1a1a' }}>
                                <td style={{ padding: '12px' }}>{new Date(r.timestamp).toLocaleString('ru-RU')}</td>
                                <td style={{ padding: '12px' }}>{r.queue_name}</td>
                                <td style={{ padding: '12px', color: '#88B0D3' }}>{r.character_name}</td>
                                <td style={{ padding: '12px' }}>{r.issued_by}</td>
                                <td style={{ padding: '12px' }}>
                                    <span style={{ 
                                        padding: '2px 6px', 
                                        borderRadius: '4px', 
                                        fontSize: '0.7rem',
                                        backgroundColor: r.record_type === 'warning' ? 'rgba(255, 170, 0, 0.1)' : 'rgba(72, 187, 120, 0.1)',
                                        color: r.record_type === 'warning' ? '#ffaa00' : '#48bb78'
                                    }}>
                                        {r.record_type === 'warning' ? 'ПРЕД' : 'НАГРАДА'}
                                    </span>
                                </td>
                                <td style={{ padding: '12px', textAlign: 'right' }}>
                                    <button 
                                        onClick={() => handleDelete(r.id)}
                                        style={{ background: 'none', border: 'none', color: '#ff4d4d', cursor: 'pointer', fontSize: '1rem' }}
                                        title="Удалить"
                                    >
                                        🗑️
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginTop: '10px' }}>
                <button 
                    disabled={page === 0} 
                    onClick={() => setPage(p => p - 1)}
                    style={{ background: '#1a1a1a', color: '#ccc', border: '1px solid #333', padding: '5px 15px', borderRadius: '4px', cursor: 'pointer', opacity: page === 0 ? 0.5 : 1 }}
                >
                    Назад
                </button>
                <span style={{ color: '#888', display: 'flex', alignItems: 'center' }}>
                    Стр. {page + 1} из {Math.ceil(total / limit) || 1}
                </span>
                <button 
                    disabled={(page + 1) * limit >= total} 
                    onClick={() => setPage(p => p + 1)}
                    style={{ background: '#1a1a1a', color: '#ccc', border: '1px solid #333', padding: '5px 15px', borderRadius: '4px', cursor: 'pointer', opacity: (page + 1) * limit >= total ? 0.5 : 1 }}
                >
                    Вперед
                </button>
            </div>
        </div>
    );
}
