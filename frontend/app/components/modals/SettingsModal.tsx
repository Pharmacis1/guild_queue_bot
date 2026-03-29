"use client";

import React, { useState, useEffect } from 'react';
import { 
    InitData, 
    ProfileResponse, 
    fetchProfile, 
    linkCharacter, 
    unlinkCharacter, 
    updateCharacterNickname,
    addAfkHistory,
    updateProfile,
    deleteAfkHistory,
    cancelCharacterRequest,
    setMainCharacter
} from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';
import styles from '../../player/[roleId]/ProfileLite.module.css';

interface SettingsModalProps {
    data: InitData | null;
    onClose: () => void;
    onRefresh?: () => void;
    initialShowAfk?: boolean;
}

export default function SettingsModal({ data, onClose, onRefresh, initialShowAfk }: SettingsModalProps) {
    const [profile, setProfile] = useState<ProfileResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [newCharNickname, setNewCharNickname] = useState('');
    const [editingChar, setEditingChar] = useState<{ roleId: number; nickname: string } | null>(null);
    const [isClosing, setIsClosing] = useState(false);

    // AFK states
    const [afkStart, setAfkStart] = useState(new Date().toISOString().split('T')[0]);
    const [afkEnd, setAfkEnd] = useState('');
    const [afkReason, setAfkReason] = useState('');
    const [showAfkForm, setShowAfkForm] = useState(initialShowAfk || false);

    const loadProfile = async () => {
        if (data?.user?.main_role_id) {
            setLoading(true);
            try {
                const res = await fetchProfile(data.user.main_role_id);
                setProfile(res);
            } finally {
                setLoading(false);
            }
        }
    };

    useEffect(() => {
        loadProfile();
    }, [data]);

    const handleClose = () => {
        setIsClosing(true);
        setTimeout(onClose, 200);
    };

    const handleLink = async () => {
        const nick = newCharNickname.trim();
        if (!nick || !data?.user?.id) return;
        try {
            const res = await linkCharacter(data.user.id, nick);
            if (res.status === 'ok' || res.status === 'pending') {
                setNewCharNickname('');
                loadProfile();
                if (onRefresh) onRefresh();
                if (res.status === 'pending') {
                    alert("Заявка на добавление отправлена Мастеру. Ожидайте подтверждения.");
                }
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (e: any) {
            alert("Ошибка при привязке: " + e.message);
        }
    };

    const handleCancelRequest = async () => {
        if (!data?.user?.main_role_id) return;
        if (!confirm("Отменить текущую заявку на добавление персонажа?")) return;
        try {
            await cancelCharacterRequest(data.user.main_role_id);
            loadProfile();
            if (onRefresh) onRefresh();
        } catch (e: any) {
            alert("Ошибка отмены: " + e.message);
        }
    };

    const handleUnlink = async (charRoleId: number, nickname: string) => {
        if (!confirm(`Отвязать персонажа ${nickname}?`)) return;
        try {
            const res = await unlinkCharacter(charRoleId, nickname);
            if (res.status === 'ok') {
                loadProfile();
                if (onRefresh) onRefresh();
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (e: any) {
            alert("Ошибка при отвязке: " + e.message);
        }
    };

    const handleToggleMain = async (charRoleId: number) => {
        if (!data?.user?.main_role_id) return;
        try {
            await setMainCharacter(data.user.main_role_id, charRoleId);
            loadProfile();
            if (onRefresh) onRefresh();
        } catch (e: any) {
            alert("Ошибка: " + e.message);
        }
    };

    const handleEditNickname = async () => {
        if (!editingChar || !data?.user?.main_role_id) return;
        try {
            await updateCharacterNickname(data.user.main_role_id, editingChar.roleId, editingChar.nickname);
            setEditingChar(null);
            loadProfile();
            if (onRefresh) onRefresh();
        } catch (e: any) {
            alert("Ошибка при изменении ника: " + e.message);
        }
    };

    return (
        <div className={`modal fade show d-block ${isClosing ? styles.modalAnimateOut : styles.modalAnimateIn}`} style={{ backgroundColor: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(10px)', zIndex: 100000 }}>
            <div className="modal-dialog modal-dialog-centered">
                <div className="modal-content" style={{ background: '#0a0a0a', border: '1px solid #333', borderRadius: '16px', color: '#fff' }}>
                    <div className="modal-header" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)', padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h5 className="modal-title" style={{ fontSize: '14px', fontWeight: '800', textTransform: 'uppercase', letterSpacing: '1px', margin: 0, color: 'rgba(255, 255, 255, 0.4)' }}>
                            {showAfkForm ? 'Отсутствие' : 'Настройки'}
                        </h5>
                        <button 
                            onClick={handleClose}
                            style={{
                                background: 'rgba(255,255,255,0.05)',
                                border: '1px solid rgba(255,255,255,0.1)',
                                color: '#ccc',
                                borderRadius: '8px',
                                padding: '4px 12px',
                                fontSize: '11px',
                                fontWeight: 'bold',
                                textTransform: 'uppercase'
                            }}
                        >
                            Назад
                        </button>
                    </div>
                    <div className="modal-body" style={{ padding: '20px' }}>
                        
                        {showAfkForm ? (
                            <div className={styles.afkSection}>
                                <div className={styles.afkHeader}>
                                    <span style={{ fontSize: '1.5rem' }}>☕</span>
                                    <h6 style={{ margin: 0, fontWeight: 'bold' }}>Параметры отсутствия</h6>
                                </div>
                                
                                <div className={styles.afkForm}>
                                    <div className={styles.inputGroup}>
                                        <label>Дата начала</label>
                                        <input 
                                            type="date" 
                                            className={styles.input} 
                                            value={afkStart} 
                                            onChange={e => setAfkStart(e.target.value)} 
                                        />
                                    </div>
                                    <div className={styles.inputGroup}>
                                        <label>Дата окончания</label>
                                        <input 
                                            type="date" 
                                            className={styles.input} 
                                            value={afkEnd} 
                                            onChange={e => setAfkEnd(e.target.value)} 
                                        />
                                    </div>
                                    <div className={styles.inputGroup}>
                                        <label>Причина (необязательно)</label>
                                        <input 
                                            type="text" 
                                            className={styles.input} 
                                            placeholder="Напр. Отпуск, Ремонт..."
                                            value={afkReason} 
                                            onChange={e => setAfkReason(e.target.value)} 
                                        />
                                    </div>
                                    <button 
                                        className={styles.btnDark} 
                                        style={{ marginTop: '10px' }}
                                        onClick={async () => {
                                            if (!data?.user?.main_role_id || !afkStart || !afkEnd) {
                                                alert("Укажите период");
                                                return;
                                            }
                                            try {
                                                const res = await updateProfile(data.user.main_role_id, {
                                                    afk_start: afkStart,
                                                    afk_end: afkEnd,
                                                    afk_reason: afkReason
                                                });
                                                if (res.status === 'ok') {
                                                    alert("Статус отсутствия обновлен");
                                                    loadProfile();
                                                    if (onRefresh) onRefresh();
                                                    setAfkReason('');
                                                }
                                            } catch (e: any) {
                                                alert("Ошибка: " + e.message);
                                            }
                                        }}
                                    >
                                        💾 Сохранить
                                    </button>
                                </div>

                                {profile?.afk_history && profile.afk_history.length > 0 && (
                                    <div className={styles.afkHistory}>
                                        <h6 style={{ fontSize: '0.85rem', color: '#666', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '12px', marginTop: '20px' }}>
                                            История периодов
                                        </h6>
                                        <div className={styles.historyList}>
                                            {profile.afk_history.map(item => (
                                                <div key={item.id} className={styles.historyItem}>
                                                    <div style={{ flex: 1 }}>
                                                        <div style={{ fontSize: '0.9rem', color: '#fff' }}>
                                                            {item.start} — {item.end}
                                                        </div>
                                                        {item.reason && (
                                                            <div style={{ fontSize: '0.75rem', color: '#888' }}>
                                                                {item.reason}
                                                            </div>
                                                        )}
                                                    </div>
                                                    <button 
                                                        className={styles.btnDeleteSmall}
                                                        onClick={async () => {
                                                            if (!confirm("Удалить этот период из истории?")) return;
                                                            try {
                                                                await deleteAfkHistory(item.id);
                                                                loadProfile();
                                                                if (onRefresh) onRefresh();
                                                            } catch (e: any) {
                                                                alert("Ошибка: " + e.message);
                                                            }
                                                        }}
                                                    >
                                                        🗑️
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="settings-content">
                                <div className="chars-section">
                                    <h6 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)', letterSpacing: '1px', marginBottom: '15px' }}>
                                        Ваши персонажи
                                    </h6>
                                    
                                    <div className="chars-list">
                                        {profile?.linked_chars.map(char => (
                                            <div key={char.nickname} className="char-row" style={{ 
                                                background: 'rgba(255,255,255,0.03)', 
                                                borderRadius: '12px', 
                                                padding: '12px', 
                                                marginBottom: '10px',
                                                border: char.is_main ? '1px solid rgba(255, 215, 0, 0.2)' : '1px solid rgba(255,255,255,0.05)'
                                            }}>
                                                <div className="d-flex align-items-center justify-content-between">
                                                    <div className="d-flex align-items-center">
                                                        <ClassIcon classId={char.class_id} size={24} />
                                                        {editingChar?.roleId === char.role_id ? (
                                                            <div className="d-flex flex-column ms-2">
                                                                <div className="d-flex">
                                                                    <input 
                                                                        type="text" 
                                                                        className="form-control form-control-sm" 
                                                                        style={{ background: '#000', border: '1px solid #444', color: '#fff', width: '150px' }}
                                                                        value={editingChar.nickname}
                                                                        onChange={e => setEditingChar({...editingChar, nickname: e.target.value})}
                                                                    />
                                                                    <button className="btn btn-sm btn-success ms-2" onClick={handleEditNickname}>
                                                                        💾
                                                                    </button>
                                                                    <button className="btn btn-sm btn-outline-secondary ms-1" onClick={() => setEditingChar(null)}>
                                                                        ✕
                                                                    </button>
                                                                </div>
                                                                <div style={{ fontSize: '9px', color: '#ffcc00', marginTop: '5px', lineHeight: '1.2' }}>
                                                                    ⚠️ Используйте, только если ник изменен в игре.<br/>Для другого чара — кнопка «Добавить».
                                                                </div>
                                                            </div>
                                                        ) : (
                                                            <div className="ms-3">
                                                                <div className="d-flex align-items-center">
                                                                    <span style={{ fontWeight: '600', color: char.is_main ? '#ffd700' : '#fff' }}>{char.nickname}</span>
                                                                    <button 
                                                                        className="btn btn-link btn-sm p-0 ms-2" 
                                                                        style={{ color: 'rgba(255,255,255,0.2)', fontSize: '10px' }}
                                                                        onClick={() => setEditingChar({ roleId: char.role_id, nickname: char.nickname })}
                                                                    >
                                                                        ✏️
                                                                    </button>
                                                                </div>
                                                                <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.3)' }}>
                                                                    {char.is_main ? 'Основа' : 'Твин'}
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                    
                                                    <div className="d-flex align-items-center">
                                                        <button 
                                                            className={`btn btn-sm ${char.is_main ? 'btn-outline-warning' : 'btn-outline-secondary'}`}
                                                            style={{ fontSize: '9px', textTransform: 'uppercase', padding: '2px 8px' }}
                                                            onClick={() => !char.is_main && handleToggleMain(char.role_id)}
                                                            disabled={char.is_main}
                                                        >
                                                            {char.is_main ? 'Главный' : 'Сделать основой'}
                                                        </button>
                                                        
                                                        <button 
                                                            className="btn btn-link btn-sm text-danger ms-2 p-0"
                                                            style={{ textDecoration: 'none', fontSize: '14px' }}
                                                            onClick={() => handleUnlink(char.role_id, char.nickname)}
                                                        >
                                                            🗑️
                                                        </button>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {profile?.pending_request_nick ? (
                                        <div className="pending-status mt-4 p-3" style={{ background: 'rgba(255, 165, 0, 0.05)', borderRadius: '12px', border: '1px dashed rgba(255, 165, 0, 0.3)' }}>
                                            <div className="d-flex align-items-center justify-content-between">
                                                <div>
                                                    <div style={{ fontSize: '11px', color: '#ffa500', fontWeight: 'bold', textTransform: 'uppercase' }}>⏳ Заявка на проверке</div>
                                                    <div style={{ fontSize: '13px', color: '#fff' }}>{profile.pending_request_nick}</div>
                                                </div>
                                                <button className="btn btn-sm btn-outline-danger" style={{ fontSize: '10px' }} onClick={handleCancelRequest}>
                                                    Отменить
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="add-char-input mt-4">
                                            <h6 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.3)', letterSpacing: '1px', marginBottom: '10px' }}>
                                                Добавить персонажа
                                            </h6>
                                            <div className="input-group">
                                                <input 
                                                    type="text" 
                                                    className="form-control" 
                                                    placeholder="Никнейм..." 
                                                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff' }}
                                                    value={newCharNickname}
                                                    onChange={e => setNewCharNickname(e.target.value)}
                                                    onKeyPress={e => e.key === 'Enter' && handleLink()}
                                                />
                                                <button className="btn btn-primary" onClick={handleLink} style={{ background: '#333', border: 'none', fontSize: '12px' }}>
                                                    Добавить
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
