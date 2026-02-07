import React, { useEffect, useState } from 'react';
import { fetchProfile, updateProfile, ProfileResponse } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';

interface PlayerModalProps {
    roleId: number | null;
    onClose: () => void;
    onSave?: () => void;
}

const PlayerModal: React.FC<PlayerModalProps> = ({ roleId, onClose, onSave }) => {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState<ProfileResponse | null>(null);
    const [activeTab, setActiveTab] = useState<'account' | 'status' | 'links' | 'queues'>('account');

    // Form States
    const [nickname, setNickname] = useState('');
    const [classId, setClassId] = useState(-1);
    const [telegramId, setTelegramId] = useState<string>('');
    const [isMain, setIsMain] = useState(true);
    const [inClan, setInClan] = useState(true);
    const [afkStart, setAfkStart] = useState('');
    const [afkEnd, setAfkEnd] = useState('');

    useEffect(() => {
        if (roleId) {
            setLoading(true);
            fetchProfile(roleId)
                .then(res => {
                    setData(res);
                    // Init Form
                    setNickname(res.nickname || '');
                    setClassId(res.class_id);
                    setTelegramId(res.telegram_id ? String(res.telegram_id) : '');
                    setIsMain(!res.is_alt);
                    setInClan(res.in_clan);
                    setAfkStart(res.afk_start ? res.afk_start.split(' ')[0] : '');
                    setAfkEnd(res.afk_end ? res.afk_end.split(' ')[0] : '');
                })
                .catch(err => {
                    console.error("Failed to load profile", err);
                    onClose();
                })
                .finally(() => setLoading(false));

            // Add modal-open class to body
            document.body.classList.add('modal-open');
        } else {
            document.body.classList.remove('modal-open');
        }

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

    if (!roleId) return null;

    return (
        <div className="modal fade show" style={{ display: 'block', backgroundColor: 'rgba(0,0,0,0.5)' }}>
            <div className="modal-dialog" style={{ maxWidth: '480px' }}>
                <div className="modal-content">
                    {/* Header */}
                    <div className="modal-header">
                        <div className="profile-hero w-100">
                            <div className="profile-hero-icon">
                                <ClassIcon classId={classId} size={40} />
                            </div>
                            <div className="profile-hero-info">
                                <h4 className="profile-hero-name">
                                    {nickname || 'Unknown'}
                                </h4>
                                <div className="profile-hero-meta">
                                    <span>ID: {roleId}</span>
                                </div>
                            </div>
                            <div className={`status-badge ${inClan ? 'status-badge-active' : ''}`}>
                                {inClan ? '🟢 В клане' : '⚫ Вне клана'}
                            </div>
                            <button type="button" className="btn-close btn-close-white ms-2" onClick={onClose}></button>
                        </div>
                    </div>

                    {/* Tabs */}
                    <nav className="profile-tab-nav nav">
                        <button
                            className={`nav-link ${activeTab === 'account' ? 'active' : ''}`}
                            onClick={() => setActiveTab('account')}
                        >👤 Аккаунт</button>
                        <button
                            className={`nav-link ${activeTab === 'status' ? 'active' : ''}`}
                            onClick={() => setActiveTab('status')}
                        >📊 Статус</button>
                        <button
                            className={`nav-link ${activeTab === 'links' ? 'active' : ''}`}
                            onClick={() => setActiveTab('links')}
                        >🔗 Связи</button>
                    </nav>

                    {/* Body */}
                    <div className="modal-body">
                        {loading && <div className="text-center p-4">Loading...</div>}

                        {!loading && activeTab === 'account' && (
                            <div className="tab-pane active">
                                <div className="profile-form-row">
                                    <div className="profile-input-group">
                                        <label>Никнейм</label>
                                        <input
                                            type="text"
                                            className="form-control"
                                            value={nickname}
                                            onChange={(e) => setNickname(e.target.value)}
                                        />
                                    </div>
                                </div>

                                <div className="profile-input-group mt-3">
                                    <label>Telegram ID</label>
                                    <input
                                        type="text"
                                        className="form-control"
                                        value={telegramId}
                                        onChange={(e) => setTelegramId(e.target.value)}
                                        placeholder="123456789"
                                    />
                                </div>

                                <div className="profile-section-label mt-3">Тип аккаунта</div>
                                <div className="profile-toggle-group">
                                    <button
                                        type="button"
                                        className={`profile-toggle-btn ${isMain ? 'active' : ''}`}
                                        onClick={() => setIsMain(true)}
                                    >⭐ Основа</button>
                                    <button
                                        type="button"
                                        className={`profile-toggle-btn ${!isMain ? 'active' : ''}`}
                                        onClick={() => setIsMain(false)}
                                    >👤 Твин</button>
                                </div>
                            </div>
                        )}

                        {!loading && activeTab === 'status' && (
                            <div className="tab-pane active">
                                <div className="profile-section-label">Членство в клане</div>
                                <div className="profile-toggle-group mb-3">
                                    <button
                                        type="button"
                                        className={`profile-toggle-btn ${inClan ? 'active' : ''}`}
                                        onClick={() => setInClan(true)}
                                    >🟢 В клане</button>
                                    <button
                                        type="button"
                                        className={`profile-toggle-btn ${!inClan ? 'active' : ''}`}
                                        onClick={() => setInClan(false)}
                                    >⚫ Вне клана</button>
                                </div>

                                <div className="afk-card">
                                    <div className="afk-card-header">
                                        <span className="afk-card-title">🛌 Режим ОТПУСК (AFK)</span>
                                    </div>
                                    <div className="afk-card-content">
                                        <div className="d-flex gap-2">
                                            <div className="flex-grow-1">
                                                <small>С</small>
                                                <input
                                                    type="date"
                                                    className="form-control form-control-sm"
                                                    value={afkStart}
                                                    onChange={e => setAfkStart(e.target.value)}
                                                />
                                            </div>
                                            <div className="flex-grow-1">
                                                <small>По</small>
                                                <input
                                                    type="date"
                                                    className="form-control form-control-sm"
                                                    value={afkEnd}
                                                    onChange={e => setAfkEnd(e.target.value)}
                                                />
                                            </div>
                                        </div>

                                        {data?.afk_history && data.afk_history.length > 0 && (
                                            <div className="mt-3">
                                                <small className="text-muted">История:</small>
                                                <ul className="list-unstyled small text-silver">
                                                    {data.afk_history.map((h, i) => (
                                                        <li key={i}>{h.start.split(' ')[0]} - {h.end.split(' ')[0]}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}

                        {!loading && activeTab === 'links' && (
                            <div className="tab-pane active">
                                <h6 className="text-muted mt-2">Связанные персонажи</h6>
                                {data?.linked_chars.length === 0 && <p className="small text-muted">Нет связей</p>}
                                <ul className="list-group list-group-dark">
                                    {data?.linked_chars.map((c, i) => (
                                        <li key={i} className="list-group-item bg-transparent d-flex justify-content-between">
                                            <span>{c.nickname}</span>
                                            {c.is_main && <span className="badge bg-warning text-dark">MAIN</span>}
                                        </li>
                                    ))}
                                </ul>

                                {data?.party && (
                                    <>
                                        <h6 className="text-muted mt-3">Конст-Пати: {data.party.name || 'Unnamed'}</h6>
                                        <ul className="list-group list-group-dark">
                                            {data.party.members.map((m, i) => (
                                                <li key={i} className="list-group-item bg-transparent">
                                                    {m.is_leader ? '👑 ' : ''}{m.nickname}
                                                </li>
                                            ))}
                                        </ul>
                                    </>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="modal-footer">
                        <button type="button" className="btn btn-secondary" onClick={onClose}>Закрыть</button>
                        <button type="button" className="btn btn-primary" onClick={handleSave}>Сохранить</button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default PlayerModal;
