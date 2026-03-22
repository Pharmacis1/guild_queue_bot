"use client";

import React, { useState, useEffect } from 'react';
import { 
    InitData, 
    ProfileResponse, 
    fetchProfile, 
    linkCharacter, 
    unlinkCharacter, 
    updateCharacterNickname,
    addAfkHistory
} from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';

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

    useEffect(() => {
        if (data?.user?.main_role_id) {
            setLoading(true);
            fetchProfile(data.user.main_role_id)
                .then(setProfile)
                .finally(() => setLoading(false));
        }
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
            if (res.status === 'ok') {
                setNewCharNickname('');
                if (data.user?.main_role_id) fetchProfile(data.user.main_role_id).then(setProfile);
                if (onRefresh) onRefresh();
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (e: any) {
            alert("Ошибка при привязке: " + e.message);
        }
    };

    const handleUnlink = async (charRoleId: number, nickname: string) => {
        if (!confirm(`Отвязать персонажа ${nickname}?`)) return;
        try {
            const res = await unlinkCharacter(charRoleId, nickname);
            if (res.status === 'ok') {
                if (data?.user?.main_role_id) fetchProfile(data.user.main_role_id).then(setProfile);
                if (onRefresh) onRefresh();
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (e: any) {
            alert("Ошибка при отвязке: " + e.message);
        }
    };

    const handleEditNickname = async () => {
        if (!editingChar || !data?.user?.main_role_id) return;
        try {
            await updateCharacterNickname(data.user.main_role_id, editingChar.roleId, editingChar.nickname);
            setEditingChar(null);
            fetchProfile(data.user.main_role_id).then(setProfile);
            if (onRefresh) onRefresh();
        } catch (e: any) {
            alert("Ошибка при изменении ника: " + e.message);
        }
    };

    const handleSaveAfk = async () => {
        if (!data?.user?.main_role_id) return;
        try {
            const res = await addAfkHistory({ 
                role_id: data.user.main_role_id, 
                start: afkStart, 
                end: afkEnd || undefined, 
                reason: afkReason 
            });
            if (res.status === 'ok') {
                setShowAfkForm(false);
                setAfkReason('');
                setAfkEnd('');
                alert("Данные об отсутствии сохранены");
                if (onRefresh) onRefresh();
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (e: any) {
            alert("Ошибка сохранения AFK: " + e.message);
        }
    };

    return (
        <div className={`modal fade show d-block ${isClosing ? 'modal-animate-out' : ''}`} style={{ backgroundColor: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(10px)', zIndex: 100000 }}>
            <div className="modal-dialog modal-dialog-centered">
                <div className="modal-content" style={{ background: '#0a0a0a', border: '1px solid #333', borderRadius: '16px', color: '#fff' }}>
                    <div className="modal-header" style={{ borderBottom: '1px solid #222', padding: '20px' }}>
                        <h5 className="modal-title" style={{ fontFamily: 'Cinzel, serif' }}>
                            {showAfkForm ? 'Сообщить об отсутствии' : 'Настройки'}
                        </h5>
                        <button type="button" className="btn-close btn-close-white" onClick={handleClose}></button>
                    </div>
                    <div className="modal-body" style={{ padding: '20px' }}>
                        
                        {showAfkForm ? (
                            /* AFK Section ONLY */
                            <section>
                                <div style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '12px', padding: '15px', border: '1px solid #222' }}>
                                    <div className="mb-3">
                                        <label className="form-label small text-muted">С (дата)</label>
                                        <input type="date" className="form-control bg-dark text-white border-secondary" value={afkStart} onChange={e => setAfkStart(e.target.value)} />
                                    </div>
                                    <div className="mb-3">
                                        <label className="form-label small text-muted">По (дата, не обязательно)</label>
                                        <input type="date" className="form-control bg-dark text-white border-secondary" value={afkEnd} onChange={e => setAfkEnd(e.target.value)} />
                                    </div>
                                    <div className="mb-3">
                                        <label className="form-label small text-muted">Причина</label>
                                        <textarea className="form-control bg-dark text-white border-secondary" rows={3} value={afkReason} onChange={e => setAfkReason(e.target.value)} placeholder="Причина отсутствия..." />
                                    </div>
                                    <div className="d-flex flex-column gap-2 mt-2">
                                        <button className="btn btn-danger w-100" onClick={handleSaveAfk} style={{ background: '#8B0000', border: 'none', padding: '12px', fontWeight: 'bold' }}>СОХРАНИТЬ</button>
                                        <button className="btn btn-outline-secondary w-100" onClick={() => setShowAfkForm(false)}>Назад к настройкам</button>
                                    </div>
                                </div>
                            </section>
                        ) : (
                            <>
                                {/* Main Settings Section */}
                                <section className="mb-4">
                                    <h6 style={{ color: '#8B0000', textTransform: 'uppercase', fontSize: '0.8rem', letterSpacing: '2px' }}>Отсутствие (AFK)</h6>
                                    <button className="btn btn-outline-danger w-100 mt-2" onClick={() => setShowAfkForm(true)} style={{ borderColor: '#8B0000', color: '#fff' }}>
                                        ☕ Сообщить об отсутствии
                                    </button>
                                </section>

                                <section className="mb-4">
                                    <h6 style={{ color: '#8B0000', textTransform: 'uppercase', fontSize: '0.8rem', letterSpacing: '2px' }}>Мои персонажи</h6>
                                    {loading ? <div className="text-center py-3">Загрузка...</div> : (
                                        <div className="d-flex flex-column gap-2 mt-3">
                                            {profile?.linked_chars.map(char => (
                                                <div key={char.role_id} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid #222', borderRadius: '8px', padding: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                                    <div className="d-flex align-items-center gap-2">
                                                        <ClassIcon classId={char.class_id} size={24} />
                                                        {editingChar?.roleId === char.role_id ? (
                                                            <input 
                                                                type="text" 
                                                                className="form-control form-control-sm bg-dark text-white border-secondary" 
                                                                value={editingChar.nickname}
                                                                onChange={e => setEditingChar({...editingChar, nickname: e.target.value})}
                                                                onKeyDown={e => e.key === 'Enter' && handleEditNickname()}
                                                                autoFocus
                                                            />
                                                        ) : (
                                                            <span style={{ fontWeight: char.is_main ? 'bold' : 'normal', color: char.is_main ? '#fff' : '#aaa' }}>
                                                                {char.nickname} {char.is_main && <span style={{ fontSize: '0.7rem', color: '#8B0000' }}>[ОСНОВА]</span>}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div className="d-flex gap-2">
                                                        {editingChar?.roleId === char.role_id ? (
                                                            <button className="btn btn-sm btn-success" onClick={handleEditNickname}>✓</button>
                                                        ) : (
                                                            <button className="btn btn-sm btn-outline-secondary" onClick={() => setEditingChar({ roleId: char.role_id!, nickname: char.nickname })}>✎</button>
                                                        )}
                                                        <button className="btn btn-sm btn-outline-danger" onClick={() => handleUnlink(char.role_id!, char.nickname)}>🗑</button>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </section>

                                <section>
                                    <h6 style={{ color: '#8B0000', textTransform: 'uppercase', fontSize: '0.8rem', letterSpacing: '2px' }}>Привязать персонажа</h6>
                                    <div className="input-group mt-3">
                                        <input 
                                            type="text" 
                                            className="form-control bg-dark text-white border-secondary" 
                                            placeholder="Никнейм персонажа"
                                            value={newCharNickname}
                                            onChange={e => setNewCharNickname(e.target.value)}
                                        />
                                        <button className="btn btn-danger" onClick={handleLink} style={{ background: '#8B0000', border: 'none' }}>Привязать</button>
                                    </div>
                                </section>
                            </>
                        )}
                    </div>
                </div>
            </div>
            <style jsx>{`
                .modal-animate-in { animation: modalIn 0.3s ease-out; }
                .modal-animate-out { animation: modalOut 0.2s ease-in forwards; }
                @keyframes modalIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }
                @keyframes modalOut { from { opacity: 1; transform: scale(1); } to { opacity: 0; transform: scale(0.95); } }
            `}</style>
        </div>
    );
}
