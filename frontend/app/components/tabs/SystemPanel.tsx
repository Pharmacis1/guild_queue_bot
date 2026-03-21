import { useState, useEffect } from 'react';
import { 
    AdminSettings, 
    BackupFile, 
    fetchAdminSettings, 
    updateAdminSettings, 
    fetchBackups, 
    createBackup, 
    deleteBackup, 
    restoreBackup 
} from '@/lib/api';

interface SystemPanelProps {
    onBack: () => void;
}

export default function SystemPanel({ onBack }: SystemPanelProps) {
    const [settings, setSettings] = useState<AdminSettings | null>(null);
    const [backups, setBackups] = useState<BackupFile[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [s, b] = await Promise.all([fetchAdminSettings(), fetchBackups()]);
            setSettings(s);
            setBackups(b);
        } catch (e) {
            console.error("Failed to load system data:", e);
        } finally {
            setLoading(false);
        }
    };

    const handleSaveSettings = async () => {
        if (!settings) return;
        setSaving(true);
        try {
            await updateAdminSettings(settings);
            alert("Настройки сохранены!");
        } catch (e) {
            alert("Ошибка при сохранении");
        } finally {
            setSaving(false);
        }
    };

    const handleCreateBackup = async () => {
        try {
            await createBackup();
            loadData();
        } catch (e) {
            alert("Ошибка при создании бэкапа");
        }
    };

    const handleDeleteBackup = async (name: string) => {
        if (!confirm(`Удалить бэкап ${name}?`)) return;
        try {
            await deleteBackup(name);
            loadData();
        } catch (e) {
            alert("Ошибка при удалении");
        }
    };

    const handleRestoreBackup = async (name: string) => {
        const warning = `⚠️ ВНИМАНИЕ! ВОССТАНОВЛЕНИЕ БАЗЫ ДАННЫХ ⚠️\n\n` +
                      `Вы выбрали файл: ${name}\n\n` +
                      `ПОСЛЕДСТВИЯ:\n` +
                      `1. Текущая база будет перезаписана.\n` +
                      `2. Бот будет перезагружен.\n\n` +
                      `Вы уверены на 100%?`;
        
        if (!confirm(warning)) return;
        if (!confirm('ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ: Все данные после этого бэкапа будут потеряны. Продолжить?')) return;

        try {
            await restoreBackup(name);
            alert("✅ База успешно восстановлена! Бот перезагружается. Страница будет обновлена через 5 секунд.");
            setTimeout(() => window.location.reload(), 5000);
        } catch (e) {
            alert("Критическая ошибка при восстановлении");
        }
    };

    if (loading) return <div className="text-center p-5" style={{ color: '#888' }}>Загрузка системных данных...</div>;

    return (
        <div style={{ 
            maxWidth: '1100px', 
            margin: '0 auto', 
            color: '#E0E0E0',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center'
        }}>
            {/* Header with Back Button */}
            <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                marginBottom: '40px', 
                width: '100%',
                justifyContent: 'flex-start'
            }}>
                <button 
                    onClick={onBack}
                    style={{
                        background: '#1a1a1a',
                        border: '1px solid #333',
                        color: '#ccc',
                        padding: '10px 18px',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        fontSize: '0.9rem',
                        transition: 'all 0.2s',
                        fontFamily: "'Cinzel', serif",
                        marginRight: '25px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
                    }}
                    onMouseOver={(e) => {
                        e.currentTarget.style.borderColor = '#ff4d6d';
                        e.currentTarget.style.color = '#fff';
                        e.currentTarget.style.boxShadow = '0 0 10px rgba(255, 77, 109, 0.2)';
                    }}
                    onMouseOut={(e) => {
                        e.currentTarget.style.borderColor = '#333';
                        e.currentTarget.style.color = '#ccc';
                        e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)';
                    }}
                >
                    <span style={{ fontSize: '1.2rem' }}>←</span> НАЗАД
                </button>
                <h2 style={{ fontFamily: "'Cinzel', serif", margin: 0, fontSize: '2rem', color: '#fff', letterSpacing: '2px' }}>
                    ⚙️ Системные настройки
                </h2>
            </div>

            <div style={{ 
                display: 'flex', 
                flexWrap: 'wrap', 
                gap: '30px', 
                width: '100%',
                justifyContent: 'center'
            }}>
                {/* SETTINGS CARD */}
                <div style={{ 
                    flex: '1 1 400px',
                    maxWidth: '500px',
                    minWidth: '350px',
                    background: '#111', 
                    border: '1px solid #333', 
                    borderRadius: '16px', 
                    padding: '30px',
                    boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
                    display: 'flex',
                    flexDirection: 'column'
                }}>
                    <h4 style={{ fontFamily: "'Cinzel', serif", color: '#ff4d6d', marginBottom: '25px', fontSize: '1.3rem', letterSpacing: '1px', borderBottom: '1px solid #222', paddingBottom: '15px' }}>
                        Публичный лог
                    </h4>
                    
                    <div style={{ marginBottom: '25px' }}>
                        <p style={{ fontSize: '0.85rem', color: '#888', marginBottom: '20px', lineHeight: '1.5' }}>
                            Настройка автоматической отправки сводки по выдаче КХ наград в Telegram канал или группу.
                        </p>

                        <label style={{ display: 'flex', alignItems: 'center', gap: '15px', cursor: 'pointer', marginBottom: '25px', userSelect: 'none' }}>
                            <div style={{ 
                                width: '44px', 
                                height: '22px', 
                                background: settings?.public_log_enabled ? '#8B0000' : '#333', 
                                borderRadius: '11px',
                                position: 'relative',
                                transition: 'background 0.3s'
                            }}>
                                <div style={{ 
                                    width: '18px', 
                                    height: '18px', 
                                    background: '#fff', 
                                    borderRadius: '50%', 
                                    position: 'absolute',
                                    top: '2px',
                                    left: settings?.public_log_enabled ? '24px' : '2px',
                                    transition: 'left 0.3s',
                                    boxShadow: '0 2px 4px rgba(0,0,0,0.3)'
                                }} />
                                <input 
                                    type="checkbox" 
                                    checked={settings?.public_log_enabled}
                                    onChange={e => setSettings(s => s ? {...s, public_log_enabled: e.target.checked} : null)}
                                    style={{ opacity: 0, width: '100%', height: '100%', cursor: 'pointer' }}
                                />
                            </div>
                            <span style={{ fontSize: '1rem', color: settings?.public_log_enabled ? '#eee' : '#666', fontWeight: settings?.public_log_enabled ? '600' : '400' }}>
                                {settings?.public_log_enabled ? 'Отправка включена' : 'Отправка выключена'}
                            </span>
                        </label>
                        
                        <div style={{ marginBottom: '20px' }}>
                            <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                <span style={{ color: '#aaa', fontSize: '0.85rem' }}>ID Канала / Группы</span>
                            </label>
                            <input 
                                type="text" 
                                placeholder="-100..."
                                value={settings?.public_log_channel_id}
                                onChange={e => setSettings(s => s ? {...s, public_log_channel_id: e.target.value} : null)}
                                style={{
                                    width: '100%', background: '#0a0a0a', border: '1px solid #333', color: '#fff', 
                                    padding: '12px', borderRadius: '8px', outline: 'none', fontSize: '0.95rem',
                                    transition: 'border-color 0.2s'
                                }}
                                onFocus={(e) => e.target.style.borderColor = '#ff4d6d'}
                                onBlur={(e) => e.target.style.borderColor = '#333'}
                            />
                        </div>
                        
                        <div style={{ marginBottom: '10px' }}>
                            <label style={{ display: 'block', marginBottom: '8px', color: '#aaa', fontSize: '0.85rem' }}>Thread ID (ID темы)</label>
                            <input 
                                type="text" 
                                placeholder="0"
                                value={settings?.public_log_thread_id}
                                onChange={e => setSettings(s => s ? {...s, public_log_thread_id: e.target.value} : null)}
                                style={{
                                    width: '100%', background: '#0a0a0a', border: '1px solid #333', color: '#fff', 
                                    padding: '12px', borderRadius: '8px', outline: 'none', fontSize: '0.95rem',
                                    transition: 'border-color 0.2s'
                                }}
                                onFocus={(e) => e.target.style.borderColor = '#ff4d6d'}
                                onBlur={(e) => e.target.style.borderColor = '#333'}
                            />
                        </div>

                        <div style={{ 
                            background: 'rgba(255, 77, 109, 0.05)', 
                            border: '1px solid rgba(255, 77, 109, 0.1)', 
                            borderRadius: '10px', 
                            padding: '15px',
                            marginTop: '25px'
                        }}>
                            <h5 style={{ fontSize: '0.8rem', color: '#ff4d6d', marginBottom: '10px', fontWeight: 'bold' }}>💡 Подсказка по ID</h5>
                            <p style={{ fontSize: '0.8rem', color: '#888', margin: 0, lineHeight: '1.4' }}>
                                • Перешлите сообщение из канала в <b>@userinfobot</b> для получения ID.<br/>
                                • Для публичных каналов можно использовать <b>@username</b>.<br/>
                                • <b>Thread ID</b> — номер темы (0 если нет тем).
                            </p>
                        </div>
                    </div>

                    <button 
                        className="btn w-100" 
                        disabled={saving}
                        onClick={handleSaveSettings}
                        style={{ 
                            background: 'linear-gradient(135deg, #8B0000 0%, #4B0000 100%)',
                            border: '1px solid #ff4d6d33',
                            color: '#eee',
                            padding: '14px',
                            borderRadius: '8px',
                            fontWeight: 'bold',
                            marginTop: 'auto',
                            boxShadow: '0 4px 15px rgba(139, 0, 0, 0.4)',
                            transition: 'all 0.2s',
                            letterSpacing: '1px'
                        }}
                        onMouseOver={(e) => {
                            e.currentTarget.style.transform = 'translateY(-2px)';
                            e.currentTarget.style.boxShadow = '0 6px 20px rgba(139, 0, 0, 0.5)';
                        }}
                        onMouseOut={(e) => {
                            e.currentTarget.style.transform = 'translateY(0)';
                            e.currentTarget.style.boxShadow = '0 4px 15px rgba(139, 0, 0, 0.4)';
                        }}
                    >
                        {saving ? 'СОХРАНЕНИЕ...' : '💾 СОХРАНИТЬ НАСТРОЙКИ'}
                    </button>
                </div>

                {/* BACKUPS CARD */}
                <div style={{ 
                    flex: '1 1 500px',
                    maxWidth: '600px',
                    minWidth: '350px',
                    background: '#111', 
                    border: '1px solid #333', 
                    borderRadius: '16px', 
                    padding: '30px',
                    boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
                    display: 'flex',
                    flexDirection: 'column'
                }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '25px', borderBottom: '1px solid #222', paddingBottom: '15px' }}>
                        <h4 style={{ fontFamily: "'Cinzel', serif", color: '#ff4d6d', margin: 0, fontSize: '1.3rem', letterSpacing: '1px' }}>
                            Бэкапы БД
                        </h4>
                        <button 
                            onClick={handleCreateBackup}
                            style={{
                                background: 'rgba(0, 150, 255, 0.1)',
                                border: '1px solid #0096ff',
                                color: '#0096ff',
                                padding: '6px 15px',
                                borderRadius: '6px',
                                fontSize: '0.8rem',
                                fontWeight: 'bold',
                                cursor: 'pointer',
                                transition: 'all 0.2s'
                            }}
                            onMouseOver={(e) => e.currentTarget.style.background = 'rgba(0, 150, 255, 0.2)'}
                            onMouseOut={(e) => e.currentTarget.style.background = 'rgba(0, 150, 255, 0.1)'}
                        >
                            + НОВЫЙ БЭКАП
                        </button>
                    </div>

                    <div style={{ 
                        maxHeight: '480px', 
                        overflowY: 'auto', 
                        border: '1px solid #222', 
                        borderRadius: '12px',
                        background: '#0a0a0a'
                    }} className="no-scrollbar">
                        <table className="table table-dark table-hover mb-0" style={{ fontSize: '0.9rem' }}>
                            <thead style={{ position: 'sticky', top: 0, background: '#1a1a1b', zIndex: 1 }}>
                                <tr>
                                    <th style={{ borderBottom: '1px solid #333', padding: '15px' }}>Имя файла</th>
                                    <th style={{ borderBottom: '1px solid #333', padding: '15px', textAlign: 'center' }}>Размер</th>
                                    <th style={{ borderBottom: '1px solid #333', padding: '15px', textAlign: 'right' }}>Инструменты</th>
                                </tr>
                            </thead>
                            <tbody>
                                {backups.map(file => (
                                    <tr key={file.name}>
                                        <td style={{ padding: '15px', verticalAlign: 'middle' }}>
                                            <div style={{ color: '#eee', fontWeight: '500', marginBottom: '4px' }}>{file.name}</div>
                                            <div style={{ fontSize: '0.75rem', color: '#555' }}>
                                                {new Date(file.mtime * 1000).toLocaleString('ru-RU')}
                                            </div>
                                        </td>
                                        <td style={{ padding: '15px', textAlign: 'center', verticalAlign: 'middle', color: '#888' }}>
                                            {file.size_mb.toFixed(2)} MB
                                        </td>
                                        <td style={{ padding: '15px', textAlign: 'right', verticalAlign: 'middle' }}>
                                            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                                                <a 
                                                    href={`/api/dashboard/admin/backups/download/${file.name}`}
                                                    style={{ color: '#0096ff', textDecoration: 'none', transition: 'transform 0.2s', display: 'inline-block' }}
                                                    title="Скачать на ПК"
                                                    onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.2)'}
                                                    onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                                                >
                                                    📥
                                                </a>
                                                <button 
                                                    onClick={() => handleRestoreBackup(file.name)}
                                                    style={{ background: 'none', border: 'none', color: '#f6ad55', cursor: 'pointer', transition: 'transform 0.2s' }}
                                                    title="Откатить БД к этой версии"
                                                    onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.2)'}
                                                    onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                                                >
                                                    🔄
                                                </button>
                                                <button 
                                                    onClick={() => handleDeleteBackup(file.name)}
                                                    style={{ background: 'none', border: 'none', color: '#f56565', cursor: 'pointer', transition: 'transform 0.2s' }}
                                                    title="Удалить файл бэкапа"
                                                    onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.2)'}
                                                    onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                                                >
                                                    🗑️
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {backups.length === 0 && (
                                    <tr>
                                        <td colSpan={3} style={{ padding: '50px', textAlign: 'center', color: '#444', fontStyle: 'italic' }}>
                                            Список резервных копий пуст
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                    <p style={{ marginTop: '20px', color: '#555', fontSize: '0.75rem', textAlign: 'center' }}>
                        * Все операции по восстановлению требуют перезагрузки бота.
                    </p>
                </div>
            </div>
            
            <style jsx>{`
                .no-scrollbar::-webkit-scrollbar {
                    width: 6px;
                }
                .no-scrollbar::-webkit-scrollbar-track {
                    background: #111;
                }
                .no-scrollbar::-webkit-scrollbar-thumb {
                    background: #333;
                    border-radius: 3px;
                }
                .no-scrollbar::-webkit-scrollbar-thumb:hover {
                    background: #444;
                }
            `}</style>
        </div>
    );
}
