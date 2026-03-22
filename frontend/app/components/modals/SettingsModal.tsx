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
                            <div style={{ textAlign: 'center', padding: '40px 20px', color: '#666' }}>
                                <div style={{ fontSize: '2rem', marginBottom: '10px' }}>🚧</div>
                                <div style={{ fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px' }}>В разработке</div>
                                <div style={{ fontSize: '0.8rem', marginTop: '10px' }}>Функционал уведомлений об отсутствии скоро появится</div>
                                <button className="btn btn-outline-secondary w-100 mt-4" onClick={() => setShowAfkForm(false)}>Назад к настройкам</button>
                            </div>
                        ) : (
                            <div style={{ textAlign: 'center', padding: '40px 20px', color: '#666' }}>
                                <div style={{ fontSize: '2rem', marginBottom: '10px' }}>⚙️</div>
                                <div style={{ fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '1px' }}>Настройки в разработке</div>
                                <div style={{ fontSize: '0.8rem', marginTop: '10px' }}>Управление персонажами временно недоступно</div>
                                <button className="btn btn-outline-danger w-100 mt-4" onClick={() => setShowAfkForm(true)} style={{ borderColor: '#8B0000', color: '#fff' }}>
                                    ☕ Сообщить об отсутствии
                                </button>
                            </div>
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
