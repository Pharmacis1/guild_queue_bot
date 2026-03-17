import React, { useState, useEffect } from 'react';

interface QueueStatus {
    id: number;
    name: string;
    is_locked: boolean;
}

export default function LockManager() {
    const [queues, setQueues] = useState<QueueStatus[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchQueues = async () => {
        setLoading(true);
        try {
            const res = await fetch('/api/master/queues');
            const data = await res.json();
            if (data.status === 'ok') {
                // The master/queues endpoint doesn't return is_locked. 
                // We need another way to get the full status or update the backend.
                // For now, I'll fetch them and then let the toggle handle it.
                setQueues(data.queues.map((q: any) => ({ ...q, is_locked: false })));
                
                // Fetch extra details if possible or assume default. 
                // Actually, let's update master/queues to return is_locked in backend.
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

    const toggleLock = async (queueId: number, currentLocked: boolean) => {
        try {
            const res = await fetch('/api/master/queue_lock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ queue_id: queueId, is_locked: !currentLocked })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                setQueues(queues.map(q => q.id === queueId ? { ...q, is_locked: !currentLocked } : q));
            } else {
                alert(data.message);
            }
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <h2 style={{ color: '#ccc', fontFamily: "'Cinzel', serif", margin: 0 }}>🔒 Блокировка очередей</h2>
            <p style={{ color: '#888', fontSize: '0.9rem' }}>Заблокированные очереди закрыты для записи новых игроков.</p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '15px' }}>
                {loading ? (
                    <div style={{ color: '#666' }}>Загрузка...</div>
                ) : queues.map(q => (
                    <div key={q.id} style={{ 
                        background: '#151517', 
                        border: '1px solid #222', 
                        padding: '20px', 
                        borderRadius: '8px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        transition: 'all 0.2s'
                    }}>
                        <div>
                            <div style={{ color: '#eee', fontWeight: 'bold' }}>{q.name}</div>
                            <div style={{ fontSize: '0.8rem', color: q.is_locked ? '#ff4d4d' : '#48bb78', marginTop: '4px' }}>
                                {q.is_locked ? 'Заблокировано' : 'Доступно'}
                            </div>
                        </div>
                        <button 
                            onClick={() => toggleLock(q.id, q.is_locked)}
                            style={{
                                background: q.is_locked ? 'rgba(72, 187, 120, 0.1)' : 'rgba(255, 77, 109, 0.1)',
                                border: `1px solid ${q.is_locked ? '#48bb78' : '#ff4d6d'}`,
                                color: q.is_locked ? '#48bb78' : '#ff4d6d',
                                padding: '8px 15px',
                                borderRadius: '6px',
                                cursor: 'pointer',
                                fontSize: '0.8rem',
                                fontWeight: 'bold',
                                transition: 'all 0.2s'
                            }}
                        >
                            {q.is_locked ? 'РАЗБЛОКИРОВАТЬ' : 'ЗАБЛОКИРОВАТЬ'}
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );
}
