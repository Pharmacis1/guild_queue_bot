import React, { useState, useEffect } from 'react';

interface QueueDesc {
    id: number;
    name: string;
    description: string;
}

export default function ConditionsManager() {
    const [queues, setQueues] = useState<QueueDesc[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState<number | null>(null);

    const fetchQueues = async () => {
        setLoading(true);
        try {
            // Need to update master/queues to return description
            const res = await fetch('/api/master/queues');
            const data = await res.json();
            if (data.status === 'ok') {
                setQueues(data.queues);
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

    const handleSave = async (id: number, desc: string) => {
        setSaving(id);
        try {
            const res = await fetch('/api/master/queue_description', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ queue_id: id, description: desc })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                // Success
            } else {
                alert(data.message);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setSaving(null);
        }
    };

    const updateDesc = (id: number, val: string) => {
        setQueues(queues.map(q => q.id === id ? { ...q, description: val } : q));
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

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <h2 style={{ color: '#ccc', fontFamily: "'Cinzel', serif", margin: 0 }}>📝 Условия получения наград</h2>
            <p style={{ color: '#888', fontSize: '0.9rem' }}>Эти условия отображаются игрокам при записи в очередь в боте.</p>

            <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', 
                gap: '15px' 
            }}>
                {loading ? (
                    <div style={{ color: '#666' }}>Загрузка...</div>
                ) : queues.map(q => {
                    const iconFile = queueIconMap[q.name];
                    return (
                        <div key={q.id} style={{ 
                            background: '#151517', 
                            border: '1px solid #222', 
                            padding: '15px', 
                            borderRadius: '10px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '12px'
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    {iconFile && (
                                        <img 
                                            src={`/icons/queues/${iconFile}`} 
                                            alt={q.name}
                                            style={{ width: '24px', height: '24px', borderRadius: '4px' }}
                                        />
                                    )}
                                    <h3 style={{ color: '#ff4d6d', margin: 0, fontSize: '0.95rem' }}>{q.name}</h3>
                                </div>
                                <button 
                                    onClick={() => handleSave(q.id, q.description)}
                                    disabled={saving === q.id}
                                    style={{ 
                                        background: 'rgba(139, 0, 0, 0.2)', 
                                        border: '1px solid #8B0000', 
                                        color: '#fff', 
                                        padding: '4px 10px', 
                                        borderRadius: '4px', 
                                        cursor: saving === q.id ? 'wait' : 'pointer',
                                        fontSize: '0.75rem',
                                        fontWeight: 'bold'
                                    }}
                                >
                                    {saving === q.id ? '...' : 'СОХРАНИТЬ'}
                                </button>
                            </div>
                            <textarea 
                                value={q.description || ''}
                                onChange={e => updateDesc(q.id, e.target.value)}
                                placeholder="Введите условия..."
                                style={{
                                    width: '100%',
                                    minHeight: '60px',
                                    background: '#0a0a0a',
                                    border: '1px solid #333',
                                    color: '#ccc',
                                    padding: '10px',
                                    borderRadius: '6px',
                                    fontSize: '0.85rem',
                                    outline: 'none',
                                    resize: 'vertical',
                                    lineHeight: '1.4'
                                }}
                            />
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
