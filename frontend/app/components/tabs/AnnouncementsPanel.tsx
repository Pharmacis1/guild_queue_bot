import React, { useState, useEffect } from 'react';
import { sendAnnouncement } from '@/lib/api';

interface AnnouncementsPanelProps {
    onBack: () => void;
}

export default function AnnouncementsPanel({ onBack }: AnnouncementsPanelProps) {
    const [text, setText] = useState('');
    const [scheduleType, setScheduleType] = useState('now'); // now, once_future, daily, weekly
    
    const [runDate, setRunDate] = useState(''); // DD.MM.YYYY
    const [runTime, setRunTime] = useState(''); // HH:MM
    
    const [selectedDays, setSelectedDays] = useState<number[]>([]);
    
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

    const [activeAnnouncements, setActiveAnnouncements] = useState<any[]>([]);
    const [loadingAnnouncements, setLoadingAnnouncements] = useState(true);

    const fetchAnnouncements = async () => {
        setLoadingAnnouncements(true);
        try {
            const res = await fetch('/api/master/announcements');
            const data = await res.json();
            if (data.status === 'ok') {
                setActiveAnnouncements(data.announcements);
            }
        } catch (e) {
            console.error('Failed to fetch announcements', e);
        } finally {
            setLoadingAnnouncements(false);
        }
    };

    useEffect(() => {
        fetchAnnouncements();
    }, []);

    const handleDelete = async (id: number) => {
        if (!confirm('Отменить и удалить эту рассылку?')) return;
        try {
            const res = await fetch('/api/master/announcements/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id })
            });
            const data = await res.json();
            if (data.status === 'ok') {
                fetchAnnouncements(); // refresh list
            } else {
                alert(data.message || 'Ошибка удаления');
            }
        } catch (e) {
            console.error(e);
            alert('Ошибка удаления');
        }
    };

    const daysOfWeek = [
        { id: 0, name: 'Пн' },
        { id: 1, name: 'Вт' },
        { id: 2, name: 'Ср' },
        { id: 3, name: 'Чт' },
        { id: 4, name: 'Пт' },
        { id: 5, name: 'Сб' },
        { id: 6, name: 'Вс' },
    ];

    const toggleDay = (dayId: number) => {
        if (selectedDays.includes(dayId)) {
            setSelectedDays(selectedDays.filter(d => d !== dayId));
        } else {
            setSelectedDays([...selectedDays, dayId]);
        }
    };

    const handleSubmit = async () => {
        if (!text.trim()) {
            setMessage({ text: 'Введите текст объявления', type: 'error' });
            return;
        }

        let run_time_val = '';
        let days_val = '';

        if (scheduleType === 'once_future') {
            if (!runDate || !runTime) {
                setMessage({ text: 'Укажите дату и время', type: 'error' });
                return;
            }
            // runDate is YYYY-MM-DD from input type="date"
            // Backend expects DD.MM.YYYY HH:MM
            const [year, month, day] = runDate.split('-');
            if (!year || !month || !day) {
                 setMessage({ text: 'Некорректная дата', type: 'error' });
                 return;
            }
            run_time_val = `${day}.${month}.${year} ${runTime}`;
        } else if (scheduleType === 'daily') {
            if (!runTime) {
                setMessage({ text: 'Укажите время', type: 'error' });
                return;
            }
            run_time_val = runTime;
        } else if (scheduleType === 'weekly') {
            if (!runTime || selectedDays.length === 0) {
                setMessage({ text: 'Укажите время и дни недели', type: 'error' });
                return;
            }
            run_time_val = runTime;
            days_val = selectedDays.join(',');
        }

        setLoading(true);
        setMessage(null);
        try {
            const respMsg = await sendAnnouncement({
                text,
                schedule_type: scheduleType,
                run_time: run_time_val,
                days_of_week: days_val
            });
            setMessage({ text: respMsg, type: 'success' });
            setText('');
            // Optional: refresh active announcements if we scheduled for future
            if (scheduleType !== 'now') fetchAnnouncements();
        } catch (error: any) {
             setMessage({ text: error.message || 'Ошибка отправки', type: 'error' });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ maxWidth: '800px', margin: '0 auto', color: '#E0E0E0' }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: '30px' }}>
                <button 
                    onClick={onBack}
                    style={{
                        background: '#1a1a1a',
                        border: '1px solid #333',
                        color: '#ccc',
                        padding: '10px 15px',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                        transition: 'all 0.2s',
                        fontFamily: "'Cinzel', serif",
                        marginRight: '20px'
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
                    <span style={{ fontSize: '1.2rem', marginRight: '8px' }}>←</span> НАЗАД
                </button>
                <h2 style={{ fontFamily: "'Cinzel', serif", margin: 0, fontSize: '1.8rem', color: '#fff' }}>
                    📢 Рассылка объявлений
                </h2>
            </div>

            <div style={{ 
                background: '#111', 
                border: '1px solid #333', 
                borderRadius: '12px', 
                padding: '30px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
            }}>
                <div style={{ marginBottom: '20px' }}>
                    <label style={{ display: 'block', marginBottom: '10px', fontWeight: 'bold', color: '#ccc' }}>
                        Текст объявления (поддерживается HTML-разметка Telegram)
                    </label>
                    <p style={{ color: '#888', fontSize: '0.85rem', marginBottom: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ color: '#ff4d6d' }}>ℹ️</span> 
                        Рассылка уйдёт всем пользователям, зарегистрированным в боте, персонажи которых на данный момент состоят в гильдии.
                    </p>
                    <textarea 
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        placeholder="Введите текст объявления, например: <b>Внимание!</b> Сбор на КХ в 20:00."
                        style={{
                            width: '100%',
                            minHeight: '150px',
                            background: '#0a0a0a',
                            border: '1px solid #444',
                            color: '#fff',
                            padding: '15px',
                            borderRadius: '8px',
                            fontSize: '1rem',
                            resize: 'vertical',
                            outline: 'none',
                            fontFamily: 'inherit',
                            boxSizing: 'border-box'
                        }}
                        onFocus={(e) => e.target.style.borderColor = '#8B0000'}
                        onBlur={(e) => e.target.style.borderColor = '#444'}
                    />
                </div>

                <div style={{ marginBottom: '25px' }}>
                    <label style={{ display: 'block', marginBottom: '15px', fontWeight: 'bold', color: '#ccc' }}>
                        Когда отправить:
                    </label>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '15px' }}>
                        {[
                            { id: 'now', label: '⚡ Прямо сейчас' },
                            { id: 'once_future', label: '📅 В определенное время' },
                            { id: 'daily', label: '⏰ Ежедневно' },
                            { id: 'weekly', label: '📆 Еженедельно' }
                        ].map(type => (
                            <label 
                                key={type.id}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px',
                                    padding: '10px 15px',
                                    background: scheduleType === type.id ? 'rgba(139, 0, 0, 0.2)' : '#1a1a1a',
                                    border: scheduleType === type.id ? '1px solid #ff4d6d' : '1px solid #333',
                                    borderRadius: '6px',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                    userSelect: 'none'
                                }}
                            >
                                <input 
                                    type="radio" 
                                    name="scheduleType"
                                    value={type.id}
                                    checked={scheduleType === type.id}
                                    onChange={() => setScheduleType(type.id)}
                                    style={{ display: 'none' }}
                                />
                                <span style={{ color: scheduleType === type.id ? '#fff' : '#aaa' }}>
                                    {type.label}
                                </span>
                            </label>
                        ))}
                    </div>
                </div>

                {scheduleType !== 'now' && (
                    <div style={{ 
                        background: '#0a0a0a', 
                        padding: '20px', 
                        borderRadius: '8px', 
                        border: '1px solid #333',
                        marginBottom: '25px'
                    }}>
                        {scheduleType === 'once_future' && (
                            <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '8px', color: '#888', fontSize: '0.9rem' }}>Дата</label>
                                    <input 
                                        type="date" 
                                        value={runDate}
                                        onChange={(e) => setRunDate(e.target.value)}
                                        style={{
                                            background: '#151515', border: '1px solid #444', color: '#fff', 
                                            padding: '10px', borderRadius: '4px', width: '180px', outline: 'none',
                                            colorScheme: 'dark'
                                        }}
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '8px', color: '#888', fontSize: '0.9rem' }}>Время (ЧЧ:ММ) по МСК</label>
                                    <input 
                                        type="time" 
                                        value={runTime}
                                        onChange={(e) => setRunTime(e.target.value)}
                                        style={{
                                            background: '#151515', border: '1px solid #444', color: '#fff', 
                                            padding: '10px', borderRadius: '4px', width: '150px', outline: 'none',
                                            colorScheme: 'dark'
                                        }}
                                    />
                                </div>
                            </div>
                        )}

                        {scheduleType === 'daily' && (
                            <div>
                                <label style={{ display: 'block', marginBottom: '8px', color: '#888', fontSize: '0.9rem' }}>Время (ЧЧ:ММ) по МСК</label>
                                <input 
                                    type="time" 
                                    value={runTime}
                                    onChange={(e) => setRunTime(e.target.value)}
                                    style={{
                                        background: '#151515', border: '1px solid #444', color: '#fff', 
                                        padding: '10px', borderRadius: '4px', width: '150px', outline: 'none',
                                        colorScheme: 'dark'
                                    }}
                                />
                            </div>
                        )}

                        {scheduleType === 'weekly' && (
                            <div>
                                <div style={{ marginBottom: '20px' }}>
                                    <label style={{ display: 'block', marginBottom: '10px', color: '#888', fontSize: '0.9rem' }}>Дни недели</label>
                                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                                        {daysOfWeek.map(day => (
                                            <div 
                                                key={day.id}
                                                onClick={() => toggleDay(day.id)}
                                                style={{
                                                    padding: '8px 15px',
                                                    background: selectedDays.includes(day.id) ? '#8B0000' : '#151515',
                                                    border: selectedDays.includes(day.id) ? '1px solid #ff4d6d' : '1px solid #444',
                                                    borderRadius: '4px',
                                                    cursor: 'pointer',
                                                    color: selectedDays.includes(day.id) ? '#fff' : '#aaa',
                                                    fontWeight: selectedDays.includes(day.id) ? 'bold' : 'normal',
                                                    transition: 'all 0.2s',
                                                    userSelect: 'none'
                                                }}
                                            >
                                                {day.name}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '8px', color: '#888', fontSize: '0.9rem' }}>Время (ЧЧ:ММ) по МСК</label>
                                    <input 
                                        type="time" 
                                        value={runTime}
                                        onChange={(e) => setRunTime(e.target.value)}
                                        style={{
                                            background: '#151515', border: '1px solid #444', color: '#fff', 
                                            padding: '10px', borderRadius: '4px', width: '150px', outline: 'none',
                                            colorScheme: 'dark'
                                        }}
                                    />
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {message && (
                    <div style={{ 
                        padding: '15px', 
                        borderRadius: '6px', 
                        marginBottom: '20px',
                        background: message.type === 'success' ? 'rgba(0, 128, 0, 0.1)' : 'rgba(139, 0, 0, 0.1)',
                        border: message.type === 'success' ? '1px solid #008000' : '1px solid #ff4d4d',
                        color: message.type === 'success' ? '#4ade80' : '#ff4d4d'
                    }}>
                        {message.text}
                    </div>
                )}

                <button
                    onClick={handleSubmit}
                    disabled={loading}
                    style={{
                        background: 'linear-gradient(135deg, #8B0000 0%, #4B0000 100%)',
                        border: '1px solid #ff4d6d33',
                        color: '#eee',
                        padding: '12px 30px',
                        borderRadius: '6px',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        fontWeight: 'bold',
                        fontSize: '1rem',
                        letterSpacing: '1px',
                        opacity: loading ? 0.7 : 1,
                        width: '100%',
                        transition: 'all 0.2s'
                    }}
                    onMouseOver={(e) => {
                        if (!loading) {
                            e.currentTarget.style.boxShadow = '0 0 15px rgba(255, 77, 109, 0.4)';
                            e.currentTarget.style.transform = 'translateY(-2px)';
                        }
                    }}
                    onMouseOut={(e) => {
                        if (!loading) {
                            e.currentTarget.style.boxShadow = 'none';
                            e.currentTarget.style.transform = 'translateY(0)';
                        }
                    }}
                >
                    {loading ? 'ОТПРАВКА...' : (scheduleType === 'now' ? 'ОТПРАВИТЬ СЕЙЧАС' : 'ЗАПЛАНИРОВАТЬ РАССЫЛКУ')}
                </button>
            </div>

            {/* Active Announcements Section */}
            <div style={{ 
                background: '#111', 
                border: '1px solid #333', 
                borderRadius: '12px', 
                padding: '30px',
                marginTop: '30px',
                boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
            }}>
                <h3 style={{ fontFamily: "'Cinzel', serif", margin: '0 0 20px 0', fontSize: '1.4rem', color: '#fff', borderBottom: '1px solid #333', paddingBottom: '10px' }}>
                    🗓 Активные рассылки
                </h3>
                
                {loadingAnnouncements ? (
                    <div style={{ color: '#888', textAlign: 'center', padding: '20px' }}>Загрузка...</div>
                ) : activeAnnouncements.length === 0 ? (
                    <div style={{ color: '#555', textAlign: 'center', padding: '30px 20px' }}>
                        Нет активных запланированных рассылок
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                        {activeAnnouncements.map((ann) => (
                            <div key={ann.id} style={{ 
                                background: '#1a1a1a', 
                                border: '1px solid #333', 
                                borderRadius: '8px', 
                                padding: '15px',
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center'
                            }}>
                                <div style={{ flex: 1, paddingRight: '20px' }}>
                                    <div style={{ display: 'flex', gap: '10px', marginBottom: '8px', alignItems: 'center' }}>
                                        <span style={{ 
                                            background: '#ff4d6d33', 
                                            color: '#ff4d6d', 
                                            padding: '2px 8px', 
                                            borderRadius: '4px', 
                                            fontSize: '0.75rem', 
                                            fontWeight: 'bold',
                                            textTransform: 'uppercase'
                                        }}>
                                            {ann.schedule_type === 'daily' ? 'Ежедневно' : 
                                             ann.schedule_type === 'weekly' ? 'Еженедельно' : 'Разово'}
                                        </span>
                                        <span style={{ color: '#aaa', fontSize: '0.85rem' }}>
                                            {ann.run_time}
                                            {ann.days_of_week && ann.schedule_type === 'weekly' && ` (Дни: ${ann.days_of_week.split(',').map((d: string) => daysOfWeek.find(x => x.id === parseInt(d))?.name).join(', ')})`}
                                        </span>
                                    </div>
                                    <div 
                                        style={{ color: '#eee', fontSize: '0.9rem', lineHeight: '1.4' }}
                                        dangerouslySetInnerHTML={{ __html: (ann.text || '').replace(/\n/g, '<br/>') }}
                                    />
                                </div>
                                <button 
                                    onClick={() => handleDelete(ann.id)}
                                    style={{
                                        background: 'transparent',
                                        border: '1px solid #ff4d4d',
                                        color: '#ff4d4d',
                                        padding: '8px 15px',
                                        borderRadius: '4px',
                                        cursor: 'pointer',
                                        fontSize: '0.8rem',
                                        transition: 'all 0.2s',
                                        whiteSpace: 'nowrap'
                                    }}
                                    onMouseOver={(e) => {
                                        e.currentTarget.style.background = 'rgba(255, 77, 77, 0.1)';
                                    }}
                                    onMouseOut={(e) => {
                                        e.currentTarget.style.background = 'transparent';
                                    }}
                                >
                                    Удалить
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
