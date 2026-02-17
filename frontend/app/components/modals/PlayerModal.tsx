import React, { useEffect, useState } from 'react';
import { fetchProfile, updateProfile, ProfileResponse, fetchInitData, InitData, addEvent, addAfkHistory, deleteAfkHistory, deleteEvent, updatePartyName, updatePartyColor, transferPartyLeadership, kickPartyMember } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';

interface PlayerModalProps {
    roleId: number | null;
    onClose: () => void;
    onSave?: () => void;
}

const PlayerModal: React.FC<PlayerModalProps> = ({ roleId, onClose, onSave }) => {
    const [loading, setLoading] = useState(true); // Initialized to true as data fetching starts immediately
    const [data, setData] = useState<ProfileResponse | null>(null);
    const [initData, setInitData] = useState<InitData | null>(null); // New state for initData
    const [activeTab, setActiveTab] = useState<'account' | 'status' | 'links' | 'queues'>('account');
    const [isClosing, setIsClosing] = useState(false);
    const [hasChanged, setHasChanged] = useState(false);

    const handleClose = () => {
        setIsClosing(true);
        setTimeout(() => {
            if (hasChanged && onSave) onSave();
            onClose();
        }, 200); // match animation
    };

    // Form States
    const [nickname, setNickname] = useState('');
    const [classId, setClassId] = useState(1); // Default to 1 or a sensible default
    const [telegramId, setTelegramId] = useState<string>('');
    const [isMain, setIsMain] = useState(true);
    const [inClan, setInClan] = useState(false); // Default to false
    const [afkStart, setAfkStart] = useState('');
    const [afkEnd, setAfkEnd] = useState('');
    const [afkReason, setAfkReason] = useState('');
    const [showAFK, setShowAFK] = useState(false);
    const [isValourOpen, setIsValourOpen] = useState(false);

    // Queue Form States
    const [selectedQueueId, setSelectedQueueId] = useState<number>(0);
    const [queueCharName, setQueueCharName] = useState('');
    const [isAutoRequeue, setIsAutoRequeue] = useState(false);
    const [isCalendarMode, setIsCalendarMode] = useState(false);

    // Links Tab States
    const [newCharNickname, setNewCharNickname] = useState('');
    // const [newPartyMemberNickname, setNewPartyMemberNickname] = useState(''); // Removed global state
    const [showColorPicker, setShowColorPicker] = useState<number | null>(null); // store party ID

    const syncProfile = async (overrides: any = {}) => {
        if (!roleId) return;
        try {
            const res = await updateProfile(roleId, {
                nickname,
                class_id: classId,
                telegram_id: telegramId || null,
                is_alt: !isMain,
                in_clan: inClan,
                afk_start: afkStart || null,
                afk_end: afkEnd || null,
                afk_reason: afkReason || null,
                ...overrides
            });
            if (res.user_id && data && !data.user_id) {
                setData(prev => prev ? { ...prev, user_id: res.user_id } : null);
            }
            setHasChanged(true);
        } catch (error) {
            console.error("Sync error:", error);
        }
    };

    useEffect(() => {
        if (!roleId) {
            setLoading(false);
            document.body.classList.remove('modal-open');
            return;
        }

        setLoading(true);
        Promise.all([
            fetchProfile(roleId),
            fetchInitData()
        ]).then(([profile, init]) => {
            setData(profile);
            setInitData(init);

            // Populate form
            setNickname(profile.nickname || '');
            setClassId(profile.class_id);
            setInClan(profile.in_clan);
            setIsMain(!profile.is_alt);
            setTelegramId(profile.username ? `@${profile.username}` : (profile.telegram_id ? profile.telegram_id.toString() : ''));
            setAfkStart(profile.afk_start ? profile.afk_start.split(' ')[0] : '');
            setAfkEnd(profile.afk_end ? profile.afk_end.split(' ')[0] : '');
            setAfkReason(profile.afk_reason || '');

            setLoading(false);
            document.body.classList.add('modal-open');
        }).catch(err => {
            console.error("Failed to fetch profile/init data:", err);
            setLoading(false);
        });

        return () => {
            document.body.classList.remove('modal-open');
        };
    }, [roleId]);


    const handleUnlink = async (nickname: string) => {
        if (!confirm(`Отвязать персонажа ${nickname}?`)) return;
        try {
            const resp = await fetch('/api/character/unlink', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nickname })
            });
            const result = await resp.json();
            if (result.status === 'ok') {
                alert("Отвязано!");
                // Refresh data
                if (roleId) fetchProfile(roleId).then(setData);
            } else {
                alert("Ошибка: " + result.message);
            }
        } catch (e: any) {
            alert("Ошибка при отвязке: " + e.message);
        }
    };

    const handleDeleteAfk = async (id: number) => {
        if (!confirm("Удалить запись об отпуске?")) return;
        try {
            await deleteAfkHistory(id);
            // Refresh
            if (roleId) {
                const profile = await fetchProfile(roleId);
                setData(profile);
            }
        } catch (e: any) {
            alert("Ошибка при удалении: " + e.message);
        }
    };

    const handleClearAfk = async () => {
        if (!roleId) return;
        if (!confirm("Очистить текущий статус АФК?")) return;
        try {
            await updateProfile(roleId, {
                afk_start: null,
                afk_end: null,
                afk_reason: null
            });
            setAfkStart('');
            setAfkEnd('');
            setAfkReason('');
            alert("Статус АФК очищен!");
            const profile = await fetchProfile(roleId);
            setData(profile);
            if (onSave) onSave();
        } catch (e: any) {
            alert("Ошибка при очистке: " + e.message);
        }
    };

    const handleAddAfk = async () => {
        if (!roleId || !afkStart || !afkEnd) {
            alert("Выберите период (С и По)");
            return;
        }
        try {
            // 1. Update current status in 'players' table
            await updateProfile(roleId, {
                afk_start: afkStart,
                afk_end: afkEnd,
                afk_reason: afkReason
            });
            // 2. Add to history
            // Use user_id if linked, otherwise use role_id
            await addAfkHistory({
                user_id: data?.user_id || undefined,
                role_id: !data?.user_id ? roleId : undefined,
                start: afkStart,
                end: afkEnd,
                reason: afkReason
            });

            alert("Отпуск добавлен!");
            // Refresh profile to show new history
            const profile = await fetchProfile(roleId);
            setData(profile);
            if (onSave) onSave();
        } catch (e: any) {
            alert("Ошибка при добавлении отпуска: " + e.message);
        }
    };

    const handleAddValour = async (e: React.FormEvent) => {
        e.preventDefault();
        const amtInput = document.getElementById('valour-amt-input') as HTMLInputElement;
        const dateInput = (e.currentTarget as HTMLElement).closest('.valour-card-content')?.querySelector('input[type="datetime-local"]') as HTMLInputElement;
        const descInput = (e.currentTarget as HTMLElement).closest('.valour-card-content')?.querySelector('input[placeholder*="Описание"]') as HTMLInputElement;

        if (!roleId || !amtInput?.value || !dateInput?.value) {
            alert("Заполните дату и значение");
            return;
        }

        try {
            await addEvent({
                role_id: roleId,
                date: dateInput.value,
                value: parseInt(amtInput.value),
                description: descInput?.value || ""
            });
            alert("Событие добавлено!");
            // Reset amount
            if (amtInput) amtInput.value = "";
            if (descInput) descInput.value = "";
            if (onSave) onSave();
        } catch (e: any) {
            alert("Ошибка при добавлении доблести: " + e.message);
        }
    };

    const handleLeaveQueue = async (entryId: number) => {
        if (!confirm("Выйти из очереди?")) return;
        try {
            const resp = await fetch('/api/queue/leave', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entry_id: entryId })
            });
            const res = await resp.json();
            if (res.status === 'ok') {
                if (roleId) fetchProfile(roleId).then(setData);
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (err: any) {
            alert("Ошибка: " + err.message);
        }
    };

    const handleCharLink = async () => {
        const nick = newCharNickname.trim();
        if (!nick) return;
        if (!data?.user_id) {
            alert("Сначала укажите Telegram/ID и сохраните (нажав в поле и выйдя из него), чтобы создать аккаунт для привязки.");
            return;
        }
        try {
            const resp = await fetch('/api/character/link', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: data.user_id, nickname: nick })
            });
            const result = await resp.json();
            if (result.status === 'ok') {
                setNewCharNickname('');
                if (roleId) fetchProfile(roleId).then(setData);
            } else {
                alert("Ошибка: " + result.message);
            }
        } catch (e: any) {
            alert("Ошибка при привязке: " + e.message);
        }
    };

    const handlePartyAdd = async (nickname: string, targetPartyId?: number) => {
        const nick = nickname.trim();
        if (!nick || !roleId) return;

        try {
            let resp;
            if (targetPartyId) {
                // Add to existing party
                resp = await fetch('/api/party/add_member', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ party_id: targetPartyId, nickname: nick })
                });
            } else {
                // Create new party with current player as leader
                resp = await fetch('/api/party/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ leader_role_id: roleId, nickname: nick })
                });
            }

            const result = await resp.json();
            if (result.status === 'ok') {
                if (roleId) fetchProfile(roleId).then(setData);
                // Clear input if successful (handled by individual inputs)
                return true;
            } else {
                alert("Ошибка: " + result.message);
                return false;
            }
        } catch (e: any) {
            alert("Ошибка при добавлении в КП: " + e.message);
            return false;
        }
    };

    const handleDeleteEvent = async (timestamp: number) => {
        if (!confirm("Удалить это действие? Это нельзя отменить.")) return;
        if (!roleId) return;

        try {
            const res = await deleteEvent(roleId, timestamp);
            if (res.status === 'ok') {
                // Refresh
                fetchProfile(roleId).then(setData);
                alert("Удалено!");
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (e: any) {
            alert("Ошибка сети: " + e.message);
        }
    };

    const handleJoinQueue = async () => {

        if (!selectedQueueId || !queueCharName) {
            alert("Выберите очередь и персонажа");
            return;
        }
        try {
            const resp = await fetch('/api/queue/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: data?.user_id,
                    queue_id: selectedQueueId,
                    character_name: queueCharName,
                    auto_requeue: isAutoRequeue
                })
            });
            const res = await resp.json();
            if (res.status === 'ok') {
                if (roleId) fetchProfile(roleId).then(setData);
                setSelectedQueueId(0);
            } else {
                alert("Ошибка: " + res.message);
            }
        } catch (err: any) {
            alert("Ошибка: " + err.message);
        }
    };

    if (!roleId) return null;

    return (
        <div className={`modal fade show d-block ${isClosing ? 'modal-animate-out' : ''}`} id="editPlayerModal" tabIndex={-1} style={{ backgroundColor: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(10px)', transition: 'opacity 0.2s' }}>
            <div className="modal-dialog modal-dialog-centered">
                <div className={`modal-content overflow-hidden ${isClosing ? 'modal-animate-out' : 'modal-animate-in'}`} style={{ border: '1px solid rgba(139, 0, 0, 0.4)', borderRadius: '12px', boxShadow: '0 0 40px rgba(0, 0, 0, 0.8)' }}>
                    {/* Header */}
                    <div className="modal-header position-relative">
                        <button type="button" className="btn-modal-close" onClick={handleClose}>&times;</button>
                        <div className="profile-hero w-100">
                            <div className="profile-hero-icon">
                                <ClassIcon classId={classId} size={40} />
                            </div>
                            <div className="profile-hero-info">
                                <h4 className="profile-hero-name">
                                    {nickname || 'Unknown'}
                                </h4>
                                <div className="profile-hero-meta">
                                    <span>{data?.class_id !== undefined && data?.class_id !== null ? (initData?.classes[data.class_id]?.[0] || 'Unknown Class') : '...'}</span>
                                    <span>• ID: {roleId}</span>
                                </div>
                            </div>
                            <div className="header-controls">
                                <div className={`status-badge ${inClan ? 'status-badge-active' : 'status-badge-inactive'}`}>
                                    {inClan ? '🟢 В КЛАНЕ' : '⚫ ВНЕ КЛАНА'}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Tabs */}
                    <nav className="profile-tab-nav">
                        <button
                            className={`nav-link ${activeTab === 'account' ? 'active' : ''}`}
                            onClick={() => setActiveTab('account')}
                        >👤 АККАУНТ</button>
                        <button
                            className={`nav-link ${activeTab === 'status' ? 'active' : ''}`}
                            onClick={() => setActiveTab('status')}
                        >📊 СТАТУС</button>
                        <button
                            className={`nav-link ${activeTab === 'links' ? 'active' : ''}`}
                            onClick={() => setActiveTab('links')}
                        >🔗 СВЯЗИ</button>
                        <button
                            className={`nav-link ${activeTab === 'queues' ? 'active' : ''}`}
                            onClick={() => setActiveTab('queues')}
                        >📋 ОЧЕРЕДИ</button>
                    </nav>

                    {/* Body */}
                    <div className="modal-body">
                        {loading && <div className="text-center p-4">Loading...</div>}

                        {!loading && (
                            <div className="profile-tab-content">
                                {activeTab === 'account' && (
                                    <div className="tab-pane active">
                                        <div className="profile-form-row">
                                            <div className="profile-input-group">
                                                <label>Никнейм</label>
                                                <div className="profile-input-container">
                                                    <input
                                                        type="text"
                                                        className="profile-field"
                                                        value={nickname}
                                                        onChange={(e) => setNickname(e.target.value)}
                                                        onBlur={(e) => {
                                                            if (data && e.target.value !== (data.nickname || '')) syncProfile();
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                            <div className="profile-input-group">
                                                <label>Класс</label>
                                                <div className="profile-input-container">
                                                    <div style={{ marginRight: '-5px' }}>
                                                        <ClassIcon classId={classId} size={24} />
                                                    </div>
                                                    <select
                                                        className="profile-field"
                                                        value={classId}
                                                        onChange={(e) => {
                                                            const cid = parseInt(e.target.value);
                                                            setClassId(cid);
                                                            syncProfile({ class_id: cid });
                                                        }}
                                                    >
                                                        {initData && Object.entries(initData.classes).map(([id, info]) => (
                                                            <option key={id} value={id}>{(info as [string, string, string])[0]}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="profile-input-group">
                                            <label>Telegram ID / @user</label>
                                            <div className="profile-input-container">
                                                <input
                                                    type="text"
                                                    className="profile-field"
                                                    value={telegramId}
                                                    onChange={(e) => setTelegramId(e.target.value)}
                                                    onBlur={(e) => {
                                                        if (data && e.target.value !== (data.telegram_id?.toString() || '')) syncProfile();
                                                    }}
                                                />
                                                <button className="btn-field-action">✈️</button>
                                            </div>
                                        </div>

                                        <div className="profile-section-label">Тип аккаунта</div>
                                        <div className="profile-toggle-group">
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${isMain ? 'active' : ''}`}
                                                onClick={() => {
                                                    setIsMain(true);
                                                    syncProfile({ is_alt: false });
                                                }}
                                            >⭐ ОСНОВА</button>
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${!isMain ? 'active' : ''}`}
                                                onClick={() => {
                                                    setIsMain(false);
                                                    syncProfile({ is_alt: true });
                                                }}
                                            >👤 ТВИН</button>
                                        </div>
                                    </div>
                                )}

                                {activeTab === 'status' && (
                                    <div className="tab-pane active">
                                        <div className="status-section-label">ЧЛЕНСТВО В КЛАНЕ</div>
                                        <div className="profile-toggle-group mb-4">
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${inClan ? 'active' : ''}`}
                                                onClick={() => {
                                                    setInClan(true);
                                                    syncProfile({ in_clan: true });
                                                }}
                                            >🟢 В КЛАНЕ</button>
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${!inClan ? 'active' : ''}`}
                                                onClick={() => {
                                                    setInClan(false);
                                                    syncProfile({ in_clan: false });
                                                }}
                                            >⚫ ВНЕ КЛАНА</button>
                                        </div>

                                        <div className="afk-card mb-4">
                                            <div className="afk-card-header">
                                                <span className="afk-card-title">🛌 Режим ОТПУСК (AFK)</span>
                                                <button
                                                    className={`afk-history-btn ${showAFK ? 'active' : ''}`}
                                                    onClick={() => setShowAFK(!showAFK)}
                                                > История</button>
                                            </div>
                                            <div className="afk-card-content" style={{ padding: '16px 20px' }}>
                                                <div className="afk-date-row" style={{ display: 'flex', gap: '30px', marginBottom: '16px', alignItems: 'flex-start' }}>
                                                    <div style={{ flex: '0 0 160px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                        <div style={{ fontSize: '0.85rem', color: '#bbb', fontWeight: 600, letterSpacing: '0.03em', paddingLeft: '4px' }}>С</div>
                                                        <input
                                                            type="date"
                                                            value={afkStart}
                                                            onChange={e => setAfkStart(e.target.value)}
                                                            onBlur={() => syncProfile()}
                                                            style={{ colorScheme: 'dark', width: '100%', padding: '10px 12px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid #444', color: '#fff', fontSize: '0.9rem' }}
                                                        />
                                                    </div>
                                                    <div style={{ flex: '0 0 160px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                        <div style={{ fontSize: '0.85rem', color: '#bbb', fontWeight: 600, letterSpacing: '0.03em', paddingLeft: '4px' }}>ПО</div>
                                                        <input
                                                            type="date"
                                                            value={afkEnd}
                                                            onChange={e => setAfkEnd(e.target.value)}
                                                            onBlur={() => syncProfile()}
                                                            style={{ colorScheme: 'dark', width: '100%', padding: '10px 12px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid #444', color: '#fff', fontSize: '0.9rem' }}
                                                        />
                                                    </div>
                                                </div>

                                                <div style={{ marginBottom: '16px' }}>
                                                    <input
                                                        type="text"
                                                        className="profile-field"
                                                        placeholder="Причина (необязательно)"
                                                        value={afkReason}
                                                        onChange={(e) => setAfkReason(e.target.value)}
                                                        onBlur={() => syncProfile()}
                                                        style={{ padding: '10px 12px', width: '100%', boxSizing: 'border-box' }}
                                                    />
                                                </div>

                                                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
                                                    {(afkStart || afkEnd || afkReason) && (
                                                        <button
                                                            type="button"
                                                            title="Снять АФК"
                                                            onClick={handleClearAfk}
                                                            style={{
                                                                width: 'auto',
                                                                padding: '10px 20px',
                                                                borderRadius: '6px',
                                                                fontWeight: 600,
                                                                background: 'rgba(255, 255, 255, 0.05)',
                                                                border: '1px solid #444',
                                                                color: '#aaa',
                                                                fontSize: '0.85rem'
                                                            }}
                                                        >СНЯТЬ ПЕРИОД</button>
                                                    )}
                                                    <button
                                                        type="button"
                                                        title="Сохранить отпуск"
                                                        className="btn-afk-add"
                                                        onClick={handleAddAfk}
                                                        style={{ width: 'auto', padding: '10px 24px', borderRadius: '6px', fontWeight: 600 }}
                                                    >ДОБАВИТЬ ПЕРИОД</button>
                                                </div>

                                                {showAFK && (
                                                    <div className="mt-3">
                                                        {data?.afk_history && data.afk_history.length > 0 ? (
                                                            <ul className="list-unstyled small text-silver mt-1 px-2">
                                                                {data.afk_history.map((h, i) => (
                                                                    <li key={i} className="mb-1 d-flex justify-content-between align-items-center flex-nowrap" style={{ opacity: 0.9 }}>
                                                                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                                            <span className="opacity-75">• {new Date(h.start).toLocaleDateString()} - {new Date(h.end).toLocaleDateString()}</span>
                                                                            {h.reason && <span className="d-block text-muted small pl-2" style={{ fontSize: '0.85em' }}>└ {h.reason}</span>}
                                                                        </div>
                                                                        <button
                                                                            type="button"
                                                                            className="btn-delete-afk"
                                                                            onClick={() => handleDeleteAfk(h.id)}
                                                                            title="Удалить"
                                                                            style={{
                                                                                background: 'rgba(139, 0, 0, 0.2)',
                                                                                border: '1px solid rgba(139, 0, 0, 0.4)',
                                                                                borderRadius: '4px',
                                                                                color: '#ff4d4d',
                                                                                cursor: 'pointer',
                                                                                padding: '1px 8px',
                                                                                fontSize: '0.9rem',
                                                                                lineHeight: 1,
                                                                                marginLeft: '8px',
                                                                                transition: 'all 0.2s',
                                                                                display: 'flex',
                                                                                alignItems: 'center',
                                                                                justifyContent: 'center',
                                                                                height: '24px',
                                                                                flexShrink: 0
                                                                            }}
                                                                        >&times;</button>
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        ) : (
                                                            <div className="small text-muted px-2 opacity-50"><i>История отсутствует</i></div>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        <div className="valour-card">
                                            <div
                                                className="valour-card-header"
                                                onClick={() => setIsValourOpen(!isValourOpen)}
                                                style={{ cursor: 'pointer' }}
                                            >
                                                <span style={{ transition: 'transform 0.2s', transform: isValourOpen ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block' }}>
                                                    ▶
                                                </span>
                                                <span>⚔️ ДОБАВИТЬ СОБЫТИЕ (ДОБЛЕСТЬ)</span>
                                            </div>
                                            {isValourOpen && (
                                                <div className="valour-card-content">
                                                    <input
                                                        type="datetime-local"
                                                        className="valour-field w-100 mb-2"
                                                        defaultValue={new Date().toISOString().slice(0, 16)}
                                                        style={{ colorScheme: 'dark' }}
                                                    />
                                                    <div className="valour-btn-grid">
                                                        {[2, 4, 6, 7, 8, 10, 14, 24, 40, 70].map(amt => (
                                                            <button
                                                                key={amt}
                                                                type="button"
                                                                className="valour-amt-btn"
                                                                onClick={() => {
                                                                    const input = document.getElementById('valour-amt-input') as HTMLInputElement;
                                                                    if (input) input.value = amt.toString();
                                                                }}
                                                            >{amt}</button>
                                                        ))}
                                                    </div>
                                                    <div className="valour-input-group">
                                                        <input
                                                            id="valour-amt-input"
                                                            type="number"
                                                            className="valour-field"
                                                            placeholder="Знач"
                                                            style={{ width: '80px' }}
                                                        />
                                                        <input
                                                            type="text"
                                                            className="valour-field flex-grow-1"
                                                            placeholder="Описание (опционально)"
                                                        />
                                                        <button type="button" className="btn-valour-add" onClick={handleAddValour}>ADD</button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {
                                    activeTab === 'links' && (
                                        <div className="links-tab-container">
                                            <div className="links-card">
                                                <div className="links-section-header">
                                                    <span>👥</span> Другие персонажи
                                                </div>
                                                <div className="char-grid">
                                                    {data?.linked_chars.filter(c => c.nickname.toLowerCase() !== (nickname || '').toLowerCase()).map((c, i) => (
                                                        <div key={i} className="char-status-card">
                                                            <button
                                                                className="btn-char-unlink"
                                                                title="Отвязать"
                                                                onClick={() => handleUnlink(c.nickname)}
                                                            >&times;</button>
                                                            <ClassIcon classId={c.class_id || 0} size={28} />
                                                            <div className="char-status-name">{c.nickname}</div>
                                                            <div className={`char-status-type ${c.is_main ? 'is-main' : ''}`}>
                                                                <span>👤</span> {c.is_main ? 'Основа' : 'Твин'}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div className="links-action-row">
                                                    <input
                                                        type="text"
                                                        className="links-field"
                                                        placeholder="Никнейм нового персонажа"
                                                        value={newCharNickname}
                                                        onChange={(e) => setNewCharNickname(e.target.value)}
                                                        onKeyDown={(e) => e.key === 'Enter' && handleCharLink()}
                                                    />
                                                    <button type="button" className="btn-links-add" onClick={handleCharLink}>ПРИВЯЗАТЬ</button>
                                                </div>
                                            </div>

                                            <div className="links-card">
                                                <div className="links-section-header">
                                                    <span>⚔️</span> Констовая пати (КП)
                                                </div>

                                                {data?.parties && data.parties.length > 0 ? (
                                                    data.parties.map((party, pIdx) => (
                                                        <div key={party.id} className="cp-group-container" style={{ marginBottom: '20px', padding: '15px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
                                                            <div className="status-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                                                                <div className="header-left" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                                    <span style={{ fontSize: '1.2rem' }}>⚔️</span>
                                                                    <span style={{ fontSize: '0.8rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Группа КП #{pIdx + 1}</span>
                                                                </div>
                                                            </div>

                                                            <div className="status-main-info" style={{ marginBottom: '20px' }}>
                                                                {party.is_leader || initData?.user?.is_master ? (
                                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                                                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                                                                            <input
                                                                                type="text"
                                                                                className="links-field"
                                                                                placeholder="Название КП"
                                                                                defaultValue={party.name || ''}
                                                                                onBlur={(e) => {
                                                                                    if (party.id && e.target.value !== party.name) {
                                                                                        updatePartyName(party.id, e.target.value).then(() => {
                                                                                            setHasChanged(true);
                                                                                            if (roleId) fetchProfile(roleId).then(setData);
                                                                                        });
                                                                                    }
                                                                                }}
                                                                            />
                                                                            <button
                                                                                onClick={() => setShowColorPicker(showColorPicker === party.id ? null : party.id)}
                                                                                style={{
                                                                                    background: '#1a1a1a',
                                                                                    border: '1px solid #333',
                                                                                    color: '#fff',
                                                                                    padding: '6px 12px',
                                                                                    borderRadius: '6px',
                                                                                    fontSize: '0.8rem',
                                                                                    cursor: 'pointer',
                                                                                    display: 'flex',
                                                                                    alignItems: 'center',
                                                                                    gap: '8px'
                                                                                }}
                                                                            >
                                                                                {showColorPicker === party.id ? 'Закрыть палитру' : 'Выбрать цвет КП'}
                                                                                <div style={{
                                                                                    width: '12px', height: '12px', borderRadius: '50%',
                                                                                    background: party.color || '#333',
                                                                                    border: '1px solid rgba(255,255,255,0.2)'
                                                                                }} />
                                                                            </button>
                                                                        </div>

                                                                        {showColorPicker === party.id && (
                                                                            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', maxWidth: '320px', padding: '15px', background: 'rgba(0,0,0,0.3)', borderRadius: '10px', width: '100%', marginBottom: '10px', boxShadow: 'inset 0 0 10px rgba(0,0,0,0.5)' }}>
                                                                                {[
                                                                                    '#ff0055', '#00ccff', '#00ff66', '#bd00ff', '#ffff00', '#ff8800',
                                                                                    '#ff00ff', '#00ff00', '#00ffff', '#ff0000', '#ff007f', '#7f00ff',
                                                                                    '#007fff', '#00ff7f', '#7fff00', '#ff7f00', '#ff5500', '#5500ff',
                                                                                    '#00ffaa', '#aa00ff'
                                                                                ].map(c => {
                                                                                    const norm = (val: any) => (val || '').toLowerCase().trim().replace(/^(?!#)/, '#');
                                                                                    const isSelected = norm(party.color) === norm(c);
                                                                                    return (
                                                                                        <div
                                                                                            key={c}
                                                                                            title={`Выбрать цвет ${c}`}
                                                                                            onClick={() => {
                                                                                                updatePartyColor(party.id, c).then(() => {
                                                                                                    setHasChanged(true);
                                                                                                    if (roleId) fetchProfile(roleId).then(setData);
                                                                                                });
                                                                                            }}
                                                                                            style={{
                                                                                                width: isSelected ? '32px' : '28px',
                                                                                                height: isSelected ? '32px' : '28px',
                                                                                                borderRadius: '50%',
                                                                                                background: c, cursor: 'pointer',
                                                                                                border: isSelected ? '3px solid #fff' : '1px solid rgba(255,255,255,0.2)',
                                                                                                outline: isSelected ? `3px solid ${c}` : 'none',
                                                                                                outlineOffset: '2px',
                                                                                                boxShadow: isSelected ? `0 0 30px ${c}, 0 0 15px ${c}` : `0 0 5px ${c}40`,
                                                                                                transform: isSelected ? 'scale(1.3)' : 'scale(1.0)',
                                                                                                transition: 'all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
                                                                                                position: 'relative',
                                                                                                zIndex: isSelected ? 10 : 1,
                                                                                                display: 'flex',
                                                                                                alignItems: 'center',
                                                                                                justifyContent: 'center'
                                                                                            }}
                                                                                        >
                                                                                            {isSelected && (
                                                                                                <span style={{ color: '#fff', fontSize: '18px', fontWeight: 'bold', textShadow: '0 0 6px #000, 0 0 3px #000', pointerEvents: 'none' }}>✓</span>
                                                                                            )}
                                                                                        </div>
                                                                                    );
                                                                                })}
                                                                                <div
                                                                                    onClick={() => {
                                                                                        updatePartyColor(party.id, "").then(() => {
                                                                                            setHasChanged(true);
                                                                                            if (roleId) fetchProfile(roleId).then(setData);
                                                                                        });
                                                                                    }}
                                                                                    style={{
                                                                                        width: '24px', height: '24px', borderRadius: '50%',
                                                                                        background: 'transparent', cursor: 'pointer',
                                                                                        border: '1px dashed #666',
                                                                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                                                        fontSize: '14px', color: '#666',
                                                                                        transition: 'all 0.2s'
                                                                                    }}
                                                                                    title="Сбросить цвет"
                                                                                >✕</div>
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                ) : (
                                                                    <div style={{ fontSize: '1.2rem', fontWeight: 'bold', color: party.color || '#fff', textShadow: party.color ? `0 0 10px ${party.color}` : 'none' }}>
                                                                        {party.name || 'Без названия'}
                                                                    </div>
                                                                )}
                                                            </div>

                                                            <div className="char-grid">
                                                                {party.members.map((m, i) => {
                                                                    const canManage = (party.is_leader || initData?.user?.is_master);
                                                                    // Prevent kicking self or transferring to self (redundant)
                                                                    // Wait, if I am leader, can I kick myself? No, I leave.
                                                                    // If I am admin viewing someone else, I can kick them using 'party_kick' endpoint (which uses 'member_role_id').
                                                                    // 'member_role_id' here is `m.role_id`.

                                                                    return (
                                                                        <div key={i} className="char-status-card" style={{ borderLeft: m.is_leader ? '2px solid gold' : '1px solid #333', position: 'relative' }}>
                                                                            <ClassIcon classId={m.class_id || 0} size={28} />
                                                                            <div className="char-status-name">
                                                                                {m.is_leader ? '👑 ' : ''}{m.nickname}
                                                                            </div>
                                                                            <div className="char-status-type">
                                                                                <span>👤</span> {m.is_leader ? 'Лидер' : 'Участник'}
                                                                            </div>

                                                                            {canManage && !m.is_leader && (
                                                                                <div style={{ position: 'absolute', top: '4px', right: '4px', display: 'flex', gap: '4px' }}>
                                                                                    <button
                                                                                        title="Передать лидерство (Crown)"
                                                                                        onClick={() => {
                                                                                            if (confirm(`Передать лидерство игроку ${m.nickname}?`)) {
                                                                                                import('@/lib/api').then(({ transferPartyLeadership }) => {
                                                                                                    transferPartyLeadership(party.id, m.role_id).then(res => {
                                                                                                        if (res.status === 'ok') {
                                                                                                            setHasChanged(true);
                                                                                                            if (roleId) fetchProfile(roleId).then(setData);
                                                                                                        } else {
                                                                                                            alert(res.message);
                                                                                                        }
                                                                                                    });
                                                                                                });
                                                                                            }
                                                                                        }}
                                                                                        style={{
                                                                                            background: 'rgba(255, 215, 0, 0.1)', cursor: 'pointer', border: '1px solid rgba(255, 215, 0, 0.3)',
                                                                                            color: 'gold', width: '20px', height: '20px', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px'
                                                                                        }}
                                                                                    >
                                                                                        👑
                                                                                    </button>
                                                                                    <button
                                                                                        title="Исключить (Kick)"
                                                                                        onClick={() => {
                                                                                            if (confirm(`Исключить игроку ${m.nickname} из КП?`)) {
                                                                                                import('@/lib/api').then(({ kickPartyMember }) => {
                                                                                                    kickPartyMember(m.role_id).then(res => {
                                                                                                        if (res.status === 'ok') {
                                                                                                            setHasChanged(true);
                                                                                                            if (roleId) fetchProfile(roleId).then(setData);
                                                                                                        } else {
                                                                                                            alert(res.message);
                                                                                                        }
                                                                                                    });
                                                                                                });
                                                                                            }
                                                                                        }}
                                                                                        style={{
                                                                                            background: 'rgba(255, 0, 0, 0.1)', cursor: 'pointer', border: '1px solid rgba(255, 0, 0, 0.3)',
                                                                                            color: '#ff4d4d', width: '20px', height: '20px', borderRadius: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', lineHeight: 1
                                                                                        }}
                                                                                    >
                                                                                        ✕
                                                                                    </button>
                                                                                </div>
                                                                            )}
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>

                                                            {/* Add Member to THIS Party */}
                                                            {(party.is_leader || initData?.user?.is_master) && (
                                                                <div className="links-action-row mt-3">
                                                                    <input
                                                                        type="text"
                                                                        className="links-field"
                                                                        placeholder="Никнейм нового участника..."
                                                                        onKeyDown={(e) => {
                                                                            if (e.key === 'Enter') {
                                                                                const target = e.currentTarget;
                                                                                handlePartyAdd(target.value, party.id).then(ok => {
                                                                                    if (ok) target.value = '';
                                                                                });
                                                                            }
                                                                        }}
                                                                    />
                                                                    <button type="button" className="btn-links-add" onClick={(e) => {
                                                                        // Find input sibling
                                                                        const input = (e.currentTarget.previousElementSibling as HTMLInputElement);
                                                                        handlePartyAdd(input.value, party.id).then(ok => {
                                                                            if (ok) input.value = '';
                                                                        });
                                                                    }}>ДОБАВИТЬ</button>
                                                                </div>
                                                            )}
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div className="empty-state-cp" style={{ marginBottom: '20px' }}>
                                                        <div className="empty-state-icon">⚔️</div>
                                                        <div className="empty-state-text">Не состоит в КП</div>
                                                    </div>
                                                )}

                                                {(!data?.parties || data.parties.length === 0) && (
                                                    <div className="mt-4 pt-3 border-top border-secondary opacity-75">
                                                        <div className="small text-muted mb-2 text-uppercase">СОЗДАТЬ / ВСТУПИТЬ В НОВУЮ КП</div>
                                                        <div className="links-action-row">
                                                            <input
                                                                type="text"
                                                                className="links-field"
                                                                placeholder="Никнейм сопартийца для старта..."
                                                                onKeyDown={(e) => {
                                                                    if (e.key === 'Enter') {
                                                                        const target = e.currentTarget;
                                                                        handlePartyAdd(target.value).then(ok => {
                                                                            if (ok) target.value = '';
                                                                        });
                                                                    }
                                                                }}
                                                            />
                                                            <button type="button" className="btn-links-add" onClick={(e) => {
                                                                const input = (e.currentTarget.previousElementSibling as HTMLInputElement);
                                                                handlePartyAdd(input.value).then(ok => {
                                                                    if (ok) input.value = '';
                                                                });
                                                            }}>СОЗДАТЬ</button>
                                                        </div>
                                                    </div>
                                                )}

                                            </div>
                                        </div>
                                    )
                                }
                                {
                                    activeTab === 'queues' && (
                                        <div className="tab-pane active">
                                            <div className="queues-tab-container">
                                                <div className="queues-card">
                                                    <div className="queues-section-header">
                                                        <span>📋</span> Активные очереди
                                                    </div>

                                                    <div className="queues-card-body">
                                                        <div className="queues-grid">
                                                            {data?.queues.map((q, i) => (
                                                                <div key={i} className="queue-chip">
                                                                    <span className="queue-chip-icon">
                                                                        {q.auto_requeue ? '🔄' : '📅'}
                                                                    </span>
                                                                    <span className="queue-name">{q.name}</span>
                                                                    {q.character_name && (
                                                                        <span className="queue-nick-badge">{q.character_name}</span>
                                                                    )}
                                                                    <button
                                                                        className="btn-queue-remove"
                                                                        onClick={() => handleLeaveQueue(q.id)}
                                                                        title="Выйти"
                                                                    >&times;</button>
                                                                </div>
                                                            ))}
                                                            {data?.queues.length === 0 && (
                                                                <div className="empty-state-text w-100 text-center py-3">
                                                                    Нет активных очередей
                                                                </div>
                                                            )}
                                                        </div>

                                                        <div className="queues-action-row">
                                                            <select
                                                                className="queues-select"
                                                                value={selectedQueueId}
                                                                onChange={(e) => setSelectedQueueId(parseInt(e.target.value))}
                                                            >
                                                                <option value={0}>Выбрать очередь...</option>
                                                                {initData?.queue_types.map(qt => (
                                                                    <option key={qt.id} value={qt.id}>{qt.name}</option>
                                                                ))}
                                                            </select>

                                                            <select
                                                                className="queues-select queues-char-select"
                                                                value={queueCharName}
                                                                onChange={(e) => setQueueCharName(e.target.value)}
                                                            >
                                                                <option value="">Персонаж...</option>
                                                                {data?.nickname && <option value={data.nickname}>{data.nickname} (Main)</option>}
                                                                {data?.linked_chars.map(c => (
                                                                    <option key={c.nickname} value={c.nickname}>{c.nickname}</option>
                                                                ))}
                                                            </select>

                                                            <button
                                                                type="button"
                                                                className={`btn-toggle-icon ${isCalendarMode ? 'active' : ''}`}
                                                                onClick={() => setIsCalendarMode(!isCalendarMode)}
                                                                title="Календарь"
                                                            >📅</button>

                                                            <button
                                                                type="button"
                                                                className={`btn-toggle-icon ${isAutoRequeue ? 'active' : ''}`}
                                                                onClick={() => setIsAutoRequeue(!isAutoRequeue)}
                                                                title="Авто-ревайв"
                                                            >🔄</button>

                                                            <button
                                                                type="button"
                                                                className="btn-queues-add"
                                                                onClick={handleJoinQueue}
                                                            >+</button>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )
                                }
                            </div >
                        )}



                    </div >

                    <div className="modal-footer">
                        <button type="button" className="btn-modal-secondary w-100" onClick={handleClose} style={{ padding: '12px', borderRadius: '8px', fontWeight: 'bold' }}>
                            ЗАКРЫТЬ
                        </button>
                    </div>
                </div >
            </div >
        </div >
    );
};

export default PlayerModal;
