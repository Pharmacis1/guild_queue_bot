'use client';

import React, { useState, useEffect } from 'react';
import api from '@/lib/api';

interface FaqTopic {
    id: number;
    topic: string;
    content: string | null;
    updated_at: string;
    message_count: number;
}

interface FaqMessage {
    id: number;
    topic_id: number;
    text: string | null;
    photo_id: string | null;
    order_index: number;
}

interface FaqPanelProps {
    onBack?: () => void;
}

const FaqPanel: React.FC<FaqPanelProps> = ({ onBack }) => {
    const [topics, setTopics] = useState<FaqTopic[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedTopic, setSelectedTopic] = useState<FaqTopic | null>(null);
    const [topicMessages, setTopicMessages] = useState<FaqMessage[]>([]);
    const [isAddingTopic, setIsAddingTopic] = useState(false);
    const [newTopicName, setNewTopicName] = useState('');
    const [newTopicText, setNewTopicText] = useState('');
    const [aiQuestion, setAiQuestion] = useState('');
    const [aiAnswer, setAiAnswer] = useState('');
    const [aiLoading, setAiLoading] = useState(false);
    const [status, setStatus] = useState({ message: '', type: '' });

    useEffect(() => {
        fetchTopics();
    }, []);

    const fetchTopics = async () => {
        setLoading(true);
        try {
            const { data } = await api.get<FaqTopic[]>('/dashboard/admin/faq');
            setTopics(data);
        } catch (error) {
            console.error('Failed to fetch topics:', error);
            showStatus('Ошибка загрузки данных', 'error');
        } finally {
            setLoading(false);
        }
    };

    const fetchTopicDetails = async (topicId: number) => {
        try {
            const { data } = await api.get<{ topic: FaqTopic, messages: FaqMessage[] }>(`/dashboard/admin/faq/${topicId}`);
            setSelectedTopic(data.topic);
            setTopicMessages(data.messages);
        } catch (error) {
            console.error('Failed to fetch topic details:', error);
            showStatus('Ошибка при загрузке деталей темы', 'error');
        }
    };

    const handleCreateTopic = async () => {
        if (!newTopicName.trim()) {
            showStatus('Введите название темы', 'error');
            return;
        }

        try {
            await api.post('/dashboard/admin/faq', {
                topic: newTopicName,
                initial_messages: newTopicText ? [{ text: newTopicText }] : []
            });
            showStatus('Тема успешно создана!', 'success');
            setNewTopicName('');
            setNewTopicText('');
            setIsAddingTopic(false);
            fetchTopics();
        } catch (error) {
            showStatus('Ошибка при создании темы', 'error');
        }
    };

    const handleDeleteTopic = async (id: number) => {
        if (!confirm('Вы уверены, что хотите удалить эту тему и все её сообщения? Бот перестанет на неё отвечать.')) return;

        try {
            await api.delete(`/dashboard/admin/faq/${id}`);
            showStatus('Тема удалена', 'success');
            fetchTopics();
            if (selectedTopic?.id === id) setSelectedTopic(null);
        } catch (error) {
            showStatus('Ошибка при удалении', 'error');
        }
    };

    const handleAddMessage = async () => {
        if (!selectedTopic || !newTopicText.trim()) return;

        try {
            await api.post(`/dashboard/admin/faq/${selectedTopic.id}/messages`, {
                text: newTopicText
            });
            setNewTopicText('');
            fetchTopicDetails(selectedTopic.id);
            showStatus('Сообщение добавлено', 'success');
        } catch (error) {
            showStatus('Ошибка при добавлении сообщения', 'error');
        }
    };

    const handleDeleteMessage = async (msgId: number) => {
        if (!confirm('Удалить это сообщение?')) return;
        try {
            await api.delete(`/dashboard/admin/faq/messages/${msgId}`);
            if (selectedTopic) fetchTopicDetails(selectedTopic.id);
        } catch (error) {
            showStatus('Ошибка при удалении сообщения', 'error');
        }
    };

    const handleAiAsk = async () => {
        if (!aiQuestion.trim()) return;
        setAiLoading(true);
        setAiAnswer('');
        try {
            const { data } = await api.post('/dashboard/admin/faq/ask', { question: aiQuestion });
            setAiAnswer(data.answer);
        } catch (error) {
            showStatus('Ошибка при запросе к AI', 'error');
        } finally {
            setAiLoading(false);
        }
    };

    const showStatus = (message: string, type: 'success' | 'error') => {
        setStatus({ message, type });
        setTimeout(() => setStatus({ message: '', type: '' }), 3000);
    };

    const filteredTopics = topics.filter(t => 
        t.topic.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const containerStyle: React.CSSProperties = {
        padding: '20px',
        color: 'white',
        maxWidth: '1200px',
        margin: '0 auto',
        fontFamily: "'Cinzel', serif",
        display: 'flex',
        flexDirection: 'column',
    };

    const cardStyle: React.CSSProperties = {
        backgroundColor: 'rgba(20, 20, 25, 0.95)',
        border: '1px solid #333',
        borderRadius: '12px',
        padding: '25px',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 15px rgba(220, 38, 38, 0.1)',
        marginBottom: '20px',
        position: 'relative',
        overflow: 'hidden'
    };

    const buttonStyle: React.CSSProperties = {
        backgroundColor: '#dc2626',
        color: 'white',
        border: 'none',
        borderRadius: '6px',
        padding: '10px 20px',
        cursor: 'pointer',
        fontSize: '0.9rem',
        fontWeight: 'bold',
        transition: 'all 0.3s ease',
        fontFamily: "'Cinzel', serif",
        textTransform: 'uppercase',
        letterSpacing: '1px'
    };

    const inputStyle: React.CSSProperties = {
        backgroundColor: '#1a1a1a',
        border: '1px solid #333',
        borderRadius: '6px',
        padding: '12px',
        color: 'white',
        width: '100%',
        marginBottom: '15px',
        fontFamily: 'sans-serif'
    };

    const topicItemStyle: React.CSSProperties = {
        padding: '15px',
        borderBottom: '1px solid #222',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        cursor: 'pointer',
        transition: 'background-color 0.2s',
    };

    if (selectedTopic) {
        return (
            <div style={containerStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
                    <h2 style={{ fontSize: '1.8rem', textShadow: '0 0 10px rgba(220, 38, 38, 0.5)', margin: 0 }}>
                        Тема: {selectedTopic.topic}
                    </h2>
                    <button 
                        onClick={() => setSelectedTopic(null)}
                        style={{ ...buttonStyle, backgroundColor: '#333' }}
                    >
                        К списку тем
                    </button>
                </div>

                <div style={cardStyle}>
                    <h3 style={{ fontSize: '1.2rem', color: '#dc2626', marginBottom: '20px' }}>Сообщения в теме</h3>
                    
                    {topicMessages.length === 0 ? (
                        <p style={{ color: '#888', textAlign: 'center', paddingTop: '20px', paddingBottom: '20px' }}>В этой теме пока нет сообщений.</p>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                            {topicMessages.map((msg, idx) => (
                                <div key={msg.id} style={{ 
                                    backgroundColor: '#151515', 
                                    padding: '15px', 
                                    borderRadius: '8px',
                                    borderLeft: '4px solid #dc2626',
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    gap: '15px'
                                }}>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: '0.8rem', color: '#666', marginBottom: '5px' }}>Блок #{idx + 1}</div>
                                        <div style={{ fontFamily: 'sans-serif', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>{msg.text || '[Без текста]'}</div>
                                        {msg.photo_id && <div style={{ color: '#aaa', fontSize: '0.8rem', marginTop: '10px' }}>🖼️ Прикреплено фото (Telegram FileID: {msg.photo_id})</div>}
                                    </div>
                                    <button 
                                        onClick={() => handleDeleteMessage(msg.id)}
                                        style={{ backgroundColor: 'transparent', border: 'none', color: '#666', cursor: 'pointer', fontSize: '1.1rem' }}
                                        title="Удалить блок"
                                    >
                                        🗑️
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    <div style={{ marginTop: '30px', borderTop: '1px solid #222', paddingTop: '20px' }}>
                        <h4 style={{ fontSize: '1rem', color: '#dc2626', marginBottom: '15px' }}>Добавить новый блок</h4>
                        <textarea 
                            style={{ ...inputStyle, minHeight: '100px', resize: 'vertical' }}
                            placeholder="Введите текст для нового блока..."
                            value={newTopicText}
                            onChange={(e) => setNewTopicText(e.target.value)}
                        />
                        <button onClick={handleAddMessage} style={buttonStyle}>Добавить блок</button>
                    </div>
                </div>

                {status.message && (
                    <div style={{
                        padding: '10px 20px',
                        borderRadius: '6px',
                        backgroundColor: status.type === 'success' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(220, 38, 38, 0.2)',
                        border: `1px solid ${status.type === 'success' ? '#22c55e' : '#dc2626'}`,
                        color: status.type === 'success' ? '#4ade80' : '#f87171',
                        marginBottom: '20px',
                        textAlign: 'center'
                    }}>
                        {status.message}
                    </div>
                )}
            </div>
        );
    }

    return (
        <div style={containerStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                    {onBack && (
                        <button 
                            onClick={onBack}
                            style={{ ...buttonStyle, backgroundColor: '#333' }}
                        >
                            Назад
                        </button>
                    )}
                    <h2 style={{ fontSize: '2rem', textShadow: '0 0 10px rgba(220, 38, 38, 0.5)', margin: 0 }}>
                        Управление FAQ & AI
                    </h2>
                </div>
            </div>

            {/* AI Assistant Section */}
            <div style={cardStyle}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '15px' }}>
                    <span style={{ fontSize: '1.5rem' }}>🤖</span>
                    <h3 style={{ fontSize: '1.2rem', color: '#dc2626', margin: 0 }}>Ассистент Gemini (Проверка знаний)</h3>
                </div>
                
                <p style={{ fontSize: '0.9rem', color: '#aaa', marginBottom: '20px', lineHeight: '1.5' }}>
                    Здесь вы можете проверить, как нейросеть будет отвечать игрокам в Telegram по вашей базе знаний. 
                    Просто введите вопрос, как если бы вы использовали команду <code>/ask</code> в боте.
                </p>

                <div style={{ display: 'flex', gap: '10px', marginBottom: aiAnswer ? '20px' : 0 }}>
                    <input 
                        style={{ ...inputStyle, marginBottom: 0 }}
                        placeholder="Ваш вопрос к AI (например: Какие условия входа в гильдию?)"
                        value={aiQuestion}
                        onChange={(e) => setAiQuestion(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAiAsk()}
                    />
                    <button 
                        onClick={handleAiAsk} 
                        style={{ ...buttonStyle, minWidth: '120px' }}
                        disabled={aiLoading}
                    >
                        {aiLoading ? 'Думаю...' : 'Спросить'}
                    </button>
                </div>

                {aiAnswer && (
                    <div style={{ 
                        backgroundColor: 'rgba(220, 38, 38, 0.05)', 
                        border: '1px solid rgba(220, 38, 38, 0.2)', 
                        borderRadius: '8px', 
                        padding: '20px',
                        animation: 'fadeIn 0.3s ease'
                    }}>
                        <div style={{ fontSize: '0.8rem', color: '#dc2626', marginBottom: '10px', fontWeight: 'bold' }}>ОТВЕТ GEMINI:</div>
                        <div style={{ fontFamily: 'sans-serif', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>{aiAnswer}</div>
                    </div>
                )}

                <div style={{ marginTop: '20px', fontSize: '0.85rem', color: '#666', fontStyle: 'italic', borderTop: '1px solid #222', paddingTop: '15px' }}>
                    💡 Совет: Чем больше тематических сообщений добавлено в тему, тем точнее будет ответ. AI ищет наиболее похожие темы по смыслу (RAG).
                </div>
            </div>

            {isAddingTopic && (
                <div style={cardStyle}>
                    <h3 style={{ fontSize: '1.2rem', color: '#dc2626', marginBottom: '20px' }}>Новая тема базы знаний</h3>
                    <input 
                        style={inputStyle}
                        placeholder="Название темы (например: Расписание КХ)"
                        value={newTopicName}
                        onChange={(e) => setNewTopicName(e.target.value)}
                    />
                    <textarea 
                        style={{ ...inputStyle, minHeight: '100px' }}
                        placeholder="Начальный текст темы..."
                        value={newTopicText}
                        onChange={(e) => setNewTopicText(e.target.value)}
                    />
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button onClick={handleCreateTopic} style={buttonStyle}>Создать</button>
                        <button 
                            onClick={() => setIsAddingTopic(false)} 
                            style={{ ...buttonStyle, backgroundColor: '#333' }}
                        >
                            Отмена
                        </button>
                    </div>
                </div>
            )}

            <div style={cardStyle}>
                <div style={{ display: 'flex', gap: '15px', marginBottom: '20px' }}>
                    <div style={{ flex: 1 }}>
                        <input 
                            style={{ ...inputStyle, marginBottom: 0 }}
                            placeholder="🔍 Поиск по темам..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                    <button 
                        onClick={() => setIsAddingTopic(true)}
                        style={{ ...buttonStyle, whiteSpace: 'nowrap' }}
                    >
                        + Добавить тему
                    </button>
                </div>

                {loading ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>Загрузка тем...</div>
                ) : filteredTopics.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: '#888' }}>Темы не найдены.</div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                        {filteredTopics.map(topic => (
                            <div 
                                key={topic.id} 
                                style={topicItemStyle}
                                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#222'}
                                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                                onClick={() => fetchTopicDetails(topic.id)}
                            >
                                <div>
                                    <div style={{ fontSize: '1.1rem', marginBottom: '5px' }}>{topic.topic}</div>
                                    <div style={{ fontSize: '0.8rem', color: '#666' }}>
                                        {topic.message_count} блоков | Обновлено: {new Date(topic.updated_at).toLocaleDateString()}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '15px' }}>
                                    <button 
                                        onClick={(e) => { e.stopPropagation(); handleDeleteTopic(topic.id); }}
                                        style={{ backgroundColor: 'transparent', border: 'none', color: '#666', cursor: 'pointer', fontSize: '1.1rem' }}
                                        title="Удалить тему"
                                    >
                                        🗑️
                                    </button>
                                    <span style={{ color: '#dc2626', fontSize: '1.2rem' }}>➔</span>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {status.message && (
                <div style={{
                    position: 'fixed',
                    bottom: '30px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    padding: '12px 25px',
                    borderRadius: '8px',
                    backgroundColor: status.type === 'success' ? '#15803d' : '#b91c1c',
                    color: 'white',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                    zIndex: 1000,
                    transition: 'all 0.3s ease'
                }}>
                    {status.message}
                </div>
            )}
        </div>
    );
};

export default FaqPanel;
