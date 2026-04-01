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
        const inQueues = profile?.queues?.some(q => q.character_name?.toLowerCase() === nickname.toLowerCase());
        const confirmMsg = inQueues 
            ? `⚠️ Внимание: Персонаж ${nickname} записан в очереди. При отвязке он будет автоматически исключен из всех очередей!\n\nПродолжить отвязку?`
            : `Отвязать персонажа ${nickname}?`;
            
        if (!confirm(confirmMsg)) return;
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
                                                        <div className="ms-3">
                                                            <div className="d-flex align-items-center">
                                                                <span style={{ fontFamily: 'inherit', fontSize: '15px', letterSpacing: '0.5px', fontWeight: 'bold', color: char.is_main ? '#ffd700' : '#fff' }}>{char.nickname}</span>
                                                                <button 
                                                                    className="btn btn-link btn-sm p-0 ms-2" 
                                                                    style={{ color: 'rgba(255,255,255,0.4)' }}
                                                                    onClick={() => setEditingChar({ roleId: char.role_id, nickname: char.nickname })}
                                                                >
                                                                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.8 }}><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                                                                </button>
                                                            </div>
                                                            <div style={{ fontSize: '10px', color: char.is_main ? 'rgba(255, 215, 0, 0.8)' : 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                                                {char.is_main ? 'Основа' : 'Твин'}
                                                            </div>
                                                        </div>
                                                    </div>
                                                    
                                                    <div className="d-flex align-items-center">
                                                        {!char.is_main && (
                                                            <button 
                                                                className="btn btn-sm btn-outline-secondary"
                                                                style={{ fontSize: '9px', textTransform: 'uppercase', padding: '3px 8px', borderRadius: '6px' }}
                                                                onClick={() => handleToggleMain(char.role_id)}
                                                            >
                                                                Сделать основой
                                                            </button>
                                                        )}
                                                        
                                                        {!char.is_main && (
                                                            <button 
                                                                className="btn btn-link btn-sm text-danger ms-2 p-0"
                                                                style={{ textDecoration: 'none' }}
                                                                onClick={() => handleUnlink(char.role_id, char.nickname)}
                                                            >
                                                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.8 }}><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Overlay for editing nickname */}
                                    {editingChar && (
                                        <div style={{
                                            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
                                            background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)',
                                            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                            borderRadius: '16px', zIndex: 10
                                        }}>
                                            <div style={{ width: '80%', background: '#111', padding: '20px', borderRadius: '12px', border: '1px solid #333', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
                                                <h6 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)', marginBottom: '15px', letterSpacing: '1px' }}>Редактирование ника</h6>
                                                <input 
                                                    type="text" 
                                                    className="form-control mb-3" 
                                                    style={{ background: '#000', border: '1px solid #444', color: '#fff' }}
                                                    value={editingChar.nickname}
                                                    onChange={e => setEditingChar({...editingChar, nickname: e.target.value})}
                                                />
                                                <div style={{ fontSize: '11px', color: '#ffcc00', marginBottom: '15px', lineHeight: '1.4', background: 'rgba(255, 204, 0, 0.1)', padding: '10px', borderRadius: '8px' }}>
                                                    ⚠️ Используйте эту функцию, <b>только если никнейм был изменен в самой игре</b>.<br/><br/>
                                                    Для добавления нового твина закройте это окно и воспользуйтесь полем «Добавить персонажа».
                                                </div>
                                                <div className="d-flex justify-content-end" style={{ gap: '10px' }}>
                                                    <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditingChar(null)}>Отмена</button>
                                                    <button className="btn btn-sm btn-primary" style={{ background: '#4CAF50', border: 'none' }} onClick={handleEditNickname}>Сохранить</button>
                                                </div>
                                            </div>
                                        </div>
                                    )}

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
                                            <div className="d-flex" style={{ gap: '10px' }}>
                                                <input 
                                                    type="text" 
                                                    className="form-control" 
                                                    placeholder="Введите никнейм..." 
                                                    style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', borderRadius: '8px' }}
                                                    value={newCharNickname}
                                                    onChange={e => setNewCharNickname(e.target.value)}
                                                    onKeyPress={e => e.key === 'Enter' && handleLink()}
                                                />
                                                <button 
                                                    className="btn btn-primary" 
                                                    onClick={handleLink} 
                                                    style={{ background: 'rgba(255,255,255,0.1)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)', fontSize: '12px', borderRadius: '8px', padding: '0 15px', whiteSpace: 'nowrap' }}
                                                >
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
