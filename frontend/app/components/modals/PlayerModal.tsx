import React, { useEffect, useState } from 'react';
import { fetchProfile, updateProfile, ProfileResponse, fetchInitData, InitData, addEvent, addAfkHistory } from '@/lib/api';
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

    const handleClose = () => {
        setIsClosing(true);
        setTimeout(() => {
            onClose();
        }, 200); // Match animation duration
    };

    // Form States
    const [nickname, setNickname] = useState('');
    const [classId, setClassId] = useState(1); // Default to 1 or a sensible default
    const [telegramId, setTelegramId] = useState<string>('');
    const [isMain, setIsMain] = useState(true);
    const [inClan, setInClan] = useState(false); // Default to false
    const [afkStart, setAfkStart] = useState('');
    const [afkEnd, setAfkEnd] = useState('');
    const [showAFK, setShowAFK] = useState(false);
    const [isValourOpen, setIsValourOpen] = useState(false);

    // Queue Form States
    const [selectedQueueId, setSelectedQueueId] = useState<number>(0);
    const [queueCharName, setQueueCharName] = useState('');
    const [isAutoRequeue, setIsAutoRequeue] = useState(false);
    const [isCalendarMode, setIsCalendarMode] = useState(false);

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
            setTelegramId(profile.telegram_id ? profile.telegram_id.toString() : '');
            setAfkStart(profile.afk_start ? profile.afk_start.split(' ')[0] : '');
            setAfkEnd(profile.afk_end ? profile.afk_end.split(' ')[0] : '');

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

    const handleSave = async () => {
        if (!roleId) return;
        try {
            await updateProfile(roleId, {
                nickname,
                class_id: classId,
                telegram_id: telegramId || null,
                is_alt: !isMain,
                in_clan: inClan,
                afk_start: afkStart || null,
                afk_end: afkEnd || null
            });
            alert("Saved!");
            if (onSave) onSave();
            onClose();
        } catch (e: any) {
            alert("Error saving: " + e.message);
        }
    };

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

    const handleAddAfk = async () => {
        if (!roleId || !afkStart || !afkEnd) {
            alert("Выберите период (С и По)");
            return;
        }
        try {
            // 1. Update current status
            await updateProfile(roleId, {
                afk_start: afkStart,
                afk_end: afkEnd
            });
            // 2. Add to history (if we have user_id)
            if (data?.user_id) {
                await addAfkHistory({
                    user_id: data.user_id,
                    start: afkStart,
                    end: afkEnd
                });
            }
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
                                    {(nickname || 'Unknown').toUpperCase()}
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
                                                        onChange={(e) => setClassId(Number(e.target.value))}
                                                    >
                                                        {initData && Object.entries(initData.classes).map(([id, info]) => (
                                                            <option key={id} value={id}>{(info as [string, string, string])[0]}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="profile-input-group">
                                            <label>Telegram ID</label>
                                            <div className="profile-input-container">
                                                <input
                                                    type="text"
                                                    className="profile-field"
                                                    value={telegramId}
                                                    onChange={(e) => setTelegramId(e.target.value)}
                                                    placeholder="1746503476"
                                                />
                                                <button className="btn-field-action">✈️</button>
                                            </div>
                                        </div>

                                        <div className="profile-section-label">Тип аккаунта</div>
                                        <div className="profile-toggle-group">
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${isMain ? 'active' : ''}`}
                                                onClick={() => setIsMain(true)}
                                            >⭐ ОСНОВА</button>
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${!isMain ? 'active' : ''}`}
                                                onClick={() => setIsMain(false)}
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
                                                onClick={() => setInClan(true)}
                                            >🟢 В КЛАНЕ</button>
                                            <button
                                                type="button"
                                                className={`profile-toggle-btn ${!inClan ? 'active' : ''}`}
                                                onClick={() => setInClan(false)}
                                            >⚫ ВНЕ КЛАНА</button>
                                        </div>

                                        <div className="afk-card mb-4">
                                            <div className="afk-card-header">
                                                <span className="afk-card-title">🛌 Режим ОТПУСК (AFK)</span>
                                                <button
                                                    className={`afk-history-btn ${showAFK ? 'active' : ''}`}
                                                    onClick={() => setShowAFK(!showAFK)}
                                                >� История</button>
                                            </div>
                                            <div className="afk-card-content">
                                                <div className="afk-date-row">
                                                    <div className="afk-date-group">
                                                        <div className="afk-date-tag">С</div>
                                                        <input
                                                            type="date"
                                                            className="afk-date-input"
                                                            value={afkStart}
                                                            onChange={e => setAfkStart(e.target.value)}
                                                            style={{ colorScheme: 'dark' }}
                                                        />
                                                    </div>
                                                    <div className="afk-date-group">
                                                        <div className="afk-date-tag">По</div>
                                                        <input
                                                            type="date"
                                                            className="afk-date-input"
                                                            value={afkEnd}
                                                            onChange={e => setAfkEnd(e.target.value)}
                                                            style={{ colorScheme: 'dark' }}
                                                        />
                                                    </div>
                                                    <button
                                                        type="button"
                                                        title="Сохранить отпуск"
                                                        className="btn-afk-add"
                                                        onClick={handleAddAfk}
                                                    >+</button>
                                                </div>

                                                {showAFK && (
                                                    <div className="mt-3">
                                                        {data?.afk_history && data.afk_history.length > 0 ? (
                                                            <ul className="list-unstyled small text-silver mt-1 px-2">
                                                                {data.afk_history.map((h, i) => (
                                                                    <li key={i} className="mb-1 opacity-75">• {h.start.split(' ')[0]} - {h.end.split(' ')[0]}</li>
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

                                {activeTab === 'links' && (
                                    <div className="links-tab-container">
                                        <div className="links-card">
                                            <div className="links-section-header">
                                                <span>👥</span> Другие персонажи
                                            </div>
                                            <div className="char-grid">
                                                {data?.linked_chars.map((c, i) => (
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
                                                />
                                                <button type="button" className="btn-links-add">ПРИВЯЗАТЬ</button>
                                            </div>
                                        </div>

                                        <div className="links-card">
                                            <div className="links-section-header">
                                                <span>⚔️</span> Констовая пати (КП)
                                            </div>

                                            {data?.party ? (
                                                <div className="char-grid">
                                                    {data.party.members.map((m, i) => (
                                                        <div key={i} className="char-status-card">
                                                            <ClassIcon classId={m.class_id || 0} size={28} />
                                                            <div className="char-status-name">
                                                                {m.is_leader ? '👑 ' : ''}{m.nickname}
                                                            </div>
                                                            <div className="char-status-type">
                                                                <span>👤</span> {m.is_leader ? 'Лидер' : 'Участник'}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <div className="empty-state-cp">
                                                    <div className="empty-state-icon">⚔️</div>
                                                    <div className="empty-state-text">Не состоит в КП</div>
                                                </div>
                                            )}

                                            <div className="links-action-row">
                                                <input
                                                    type="text"
                                                    className="links-field"
                                                    placeholder="Никнейм участника КП"
                                                />
                                                <button type="button" className="btn-links-add">ДОБАВИТЬ</button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === 'queues' && (
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
                                )}
                            </div>
                        )}
                    </div>

                    <div className="modal-footer d-flex gap-2">
                        <button type="button" className="btn-modal-secondary flex-grow-1" onClick={handleClose}>
                            &times; Отмена
                        </button>
                        <button type="button" className="btn-ruby-action flex-grow-1" onClick={handleSave} style={{ fontSize: '0.85rem' }}>
                            💾 СОХРАНИТЬ
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PlayerModal;
